from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.activity import Activity
from app.models.activity_ml_feature import ActivityMLFeature
from app.services.quality_metrics import get_or_compute_quality_metric

FEATURE_VERSION_V1 = 1


def _build_feature_payload(activity: Activity, metric, *, feature_version: int) -> dict:
    official_distance_m = float(activity.distance_m) if activity.distance_m is not None else None
    duration_s = int(metric.duration_s)
    gps_distance_m = float(metric.distance_m_gps)
    point_count = int(metric.point_count)

    avg_speed_mps_gps = (gps_distance_m / duration_s) if duration_s > 0 else None
    distance_ratio_gps_vs_official = (
        gps_distance_m / official_distance_m
        if official_distance_m is not None and official_distance_m > 0
        else None
    )
    spikes_per_km = (metric.spike_count / (gps_distance_m / 1000.0)) if gps_distance_m > 0 else None
    stopped_fraction = (metric.stopped_time_s / duration_s) if duration_s > 0 else None
    points_per_km = (point_count / (gps_distance_m / 1000.0)) if gps_distance_m > 0 else None
    points_per_min = (point_count / (duration_s / 60.0)) if duration_s > 0 else None
    stop_segments_per_hour = (metric.stop_segments / (duration_s / 3600.0)) if duration_s > 0 else None
    spike_fraction = (metric.spike_count / point_count) if point_count > 0 else None

    metadata = {
        "name": activity.name,
        "sport_type": activity.sport_type,
        "start_date": activity.start_date.isoformat() if activity.start_date else None,
        "moving_time_s": activity.moving_time_s,
        "distance_m_official": official_distance_m,
        "elevation_gain_m": activity.elevation_gain_m,
    }
    features = {
        "point_count": point_count,
        "duration_s": duration_s,
        "distance_m_gps": gps_distance_m,
        "distance_ratio_gps_vs_official": distance_ratio_gps_vs_official,
        "avg_speed_mps_gps": avg_speed_mps_gps,
        "max_speed_mps": metric.max_speed_mps,
        "max_speed_kmh": metric.max_speed_mps * 3.6,
        "spike_count": metric.spike_count,
        "spikes_per_km": spikes_per_km,
        "stopped_time_s": metric.stopped_time_s,
        "stopped_fraction": stopped_fraction,
        "stop_segments": metric.stop_segments,
        "jitter_score": metric.jitter_score,
        "points_per_km": points_per_km,
        "points_per_min": points_per_min,
        "stop_segments_per_hour": stop_segments_per_hour,
        "spike_fraction": spike_fraction,
    }
    return {
        "activity_id": activity.id,
        "strava_activity_id": activity.strava_activity_id,
        "feature_version": feature_version,
        "metadata": metadata,
        "features": features,
    }


def upsert_activity_ml_feature(
    db: Session,
    *,
    activity_id: int,
    feature_version: int,
    features_json: dict,
) -> ActivityMLFeature:
    row = (
        db.query(ActivityMLFeature)
        .filter(ActivityMLFeature.activity_id == activity_id)
        .one_or_none()
    )
    if row is None:
        row = ActivityMLFeature(activity_id=activity_id)
        db.add(row)

    row.feature_version = feature_version
    row.features_json = features_json
    row.computed_at = datetime.now(timezone.utc)
    return row


def build_activity_features(
    db: Session,
    *,
    activity_id: int,
    feature_version: int = FEATURE_VERSION_V1,
    persist: bool = True,
) -> dict:
    activity = db.query(Activity).filter(Activity.id == activity_id).one_or_none()
    if activity is None:
        raise LookupError("Activity not found")

    metric = get_or_compute_quality_metric(
        db,
        activity_id=activity_id,
        commit_if_computed=False,
    )
    payload = _build_feature_payload(activity, metric, feature_version=feature_version)

    computed_at = metric.computed_at
    if persist:
        row = upsert_activity_ml_feature(
            db,
            activity_id=activity.id,
            feature_version=feature_version,
            features_json={
                "metadata": payload["metadata"],
                "features": payload["features"],
            },
        )
        computed_at = row.computed_at

    payload["computed_at"] = computed_at.isoformat() if computed_at else None
    return payload
