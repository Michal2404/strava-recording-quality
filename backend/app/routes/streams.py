from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from geoalchemy2.functions import ST_X, ST_Y
from sqlalchemy import text


from app.core.db import get_db
from app.models.activity import Activity
from app.models.activity_point import ActivityPoint
from app.services.ml_features import build_activity_features
from app.services.quality_metrics import (
    get_or_compute_quality_metric,
)
from app.services.stream_ingest import (
    ActivityNotFoundError,
    MissingStreamDataError,
    MissingTokenError,
    ingest_streams_for_activity,
)

router = APIRouter(prefix="/activities", tags=["streams"])


def _quality_payload(activity: Activity, metric) -> dict:
    return {
        "activity_id": activity.id,
        "name": activity.name,
        "sport_type": activity.sport_type,
        "point_count": metric.point_count,
        "duration_s": metric.duration_s,
        "distance_m_gps": metric.distance_m_gps,
        "max_speed_mps": metric.max_speed_mps,
        "max_speed_kmh": metric.max_speed_mps * 3.6,
        "spike_count": metric.spike_count,
        "stopped_time_s": metric.stopped_time_s,
        "stop_segments": metric.stop_segments,
        "jitter_score": metric.jitter_score,
        "computed_at": metric.computed_at.isoformat() if metric.computed_at else None,
        "notes": {
            "spike_speed_threshold_mps": metric.spike_speed_threshold_mps,
            "stop_speed_threshold_mps": metric.stop_speed_threshold_mps,
            "stop_min_duration_s": metric.stop_min_duration_s,
        },
    }

@router.post("/{activity_id}/ingest_streams")
def ingest_activity_streams(
    activity_id: int,
    db: Session = Depends(get_db),
):
    try:
        result = ingest_streams_for_activity(
            db,
            activity_id=activity_id,
            commit=True,
        )
    except ActivityNotFoundError:
        raise HTTPException(status_code=404, detail="Activity not found")
    except MissingTokenError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc))
    except MissingStreamDataError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))

    return {"ok": True, "points": result.points}


@router.get("/{activity_id}/track")
def get_activity_track(activity_id: int, db: Session = Depends(get_db)):
    activity = db.query(Activity).filter(Activity.id == activity_id).one_or_none()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    # Ensure points exist
    count = db.query(ActivityPoint).filter(ActivityPoint.activity_id == activity_id).count()
    if count == 0:
        raise HTTPException(status_code=404, detail="No points found. Ingest streams first.")

    # Build a LineString in PostGIS from ordered points
    # ST_MakeLine over ordered points gives us a geometry LINESTRING
    sql = text("""
        SELECT ST_AsGeoJSON(
            ST_MakeLine(geom ORDER BY seq)
        ) AS geojson
        FROM activity_points
        WHERE activity_id = :activity_id
    """)

    row = db.execute(sql, {"activity_id": activity_id}).mappings().one()
    linestring_geojson = row["geojson"]

    feature = {
        "type": "Feature",
        "geometry": None if linestring_geojson is None else __import__("json").loads(linestring_geojson),
        "properties": {
            "activity_id": activity_id,
            "name": activity.name,
            "sport_type": activity.sport_type,
            "point_count": count,
            "start_date": activity.start_date.isoformat() if activity.start_date else None,
        },
    }

    return feature


@router.get("/{activity_id}/points.geojson")
def get_activity_points_geojson(activity_id: int, db: Session = Depends(get_db)):
    activity = db.query(Activity).filter(Activity.id == activity_id).one_or_none()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    rows = (
        db.query(
            ST_X(ActivityPoint.geom),
            ST_Y(ActivityPoint.geom),
            ActivityPoint.seq,
            ActivityPoint.time_s,
            ActivityPoint.ele_m,
        )
        .filter(ActivityPoint.activity_id == activity_id)
        .order_by(ActivityPoint.seq.asc())
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No points found. Ingest streams first.")

    features = []
    for row in rows:
        lon = float(row[0])
        lat = float(row[1])
        seq = int(row[2])
        time_s = int(row[3])
        ele_m = int(row[4]) if row[4] is not None else None
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "activity_id": activity_id,
                    "seq": seq,
                    "time_s": time_s,
                    "ele_m": ele_m,
                },
            }
        )

    return {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "activity_id": activity.id,
            "name": activity.name,
            "sport_type": activity.sport_type,
            "point_count": len(features),
            "start_date": activity.start_date.isoformat() if activity.start_date else None,
        },
    }


@router.get("/{activity_id}/quality")
def activity_quality(activity_id: int, db: Session = Depends(get_db)):
    # Ensure activity exists.
    activity = db.query(Activity).filter(Activity.id == activity_id).one_or_none()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    try:
        metric = get_or_compute_quality_metric(
            db,
            activity_id=activity_id,
            commit_if_computed=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return _quality_payload(activity, metric)


@router.get("/{activity_id}/features")
def activity_features(activity_id: int, db: Session = Depends(get_db)):
    try:
        payload = build_activity_features(db, activity_id=activity_id, persist=True)
        db.commit()
    except LookupError:
        raise HTTPException(status_code=404, detail="Activity not found")
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc))
    return payload
