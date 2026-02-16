from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import text
from sqlalchemy import select
from geoalchemy2.functions import ST_X, ST_Y
from app.services.quality import compute_quality


from app.core.db import get_db
from app.models.activity import Activity
from app.models.activity_point import ActivityPoint
from app.models.strava_token import StravaToken
from app.models.user import User
from app.services.strava_session import build_strava_client, persist_refreshed_token

router = APIRouter(prefix="/activities", tags=["streams"])

@router.post("/{activity_id}/ingest_streams")
def ingest_activity_streams(
    activity_id: int,
    db: Session = Depends(get_db),
):
    activity = db.query(Activity).filter(Activity.id == activity_id).one_or_none()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    user = db.query(User).filter(User.id == activity.user_id).one()
    token = db.query(StravaToken).filter(StravaToken.user_id == user.id).one()

    client = build_strava_client(token)
    streams = client.get_activity_streams(activity.strava_activity_id)
    persist_refreshed_token(db, token, client, commit=True)

    latlng = streams.get("latlng", {}).get("data")
    times = streams.get("time", {}).get("data")
    altitude = streams.get("altitude", {}).get("data")

    if not latlng or not times:
        raise HTTPException(status_code=400, detail="Missing latlng or time streams")

    # Idempotency: delete existing points for this activity
    db.query(ActivityPoint).filter(ActivityPoint.activity_id == activity.id).delete()

    points = []
    for i, (coord, t) in enumerate(zip(latlng, times)):
        lon, lat = coord[1], coord[0]

        p = ActivityPoint(
            activity_id=activity.id,
            seq=i,
            time_s=t,
            geom=from_shape(Point(lon, lat), srid=4326),
            ele_m=altitude[i] if altitude else None,
        )
        points.append(p)

    db.bulk_save_objects(points)
    db.commit()

    return {"ok": True, "points": len(points)}


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


@router.get("/{activity_id}/quality")
def activity_quality(activity_id: int, db: Session = Depends(get_db)):
    # ensure activity exists
    activity = db.query(Activity).filter(Activity.id == activity_id).one_or_none()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    # fetch ordered points (lat, lon, time)
    rows = (
        db.query(
            ST_Y(ActivityPoint.geom),
            ST_X(ActivityPoint.geom),
            ActivityPoint.time_s,
        )
        .filter(ActivityPoint.activity_id == activity_id)
        .order_by(ActivityPoint.seq.asc())
        .all()
    )

    if len(rows) < 2:
        raise HTTPException(status_code=404, detail="Not enough points. Ingest streams first.")

    # rows are tuples: (lat, lon, time_s)
    latlons = [(float(r[0]), float(r[1])) for r in rows]
    times = [int(r[2]) for r in rows]


    report = compute_quality(latlons, times)

    return {
        "activity_id": activity_id,
        "name": activity.name,
        "sport_type": activity.sport_type,
        "point_count": report.point_count,
        "duration_s": report.duration_s,
        "distance_m_gps": report.distance_m,
        "max_speed_mps": report.max_speed_mps,
        "max_speed_kmh": report.max_speed_mps * 3.6,
        "spike_count": report.spike_count,
        "stopped_time_s": report.stopped_time_s,
        "stop_segments": report.stop_segments,
        "jitter_score": report.jitter_score,
        "notes": {
            "spike_speed_threshold_mps": 12.0,
            "stop_speed_threshold_mps": 0.6,
            "stop_min_duration_s": 10,
        },
    }
