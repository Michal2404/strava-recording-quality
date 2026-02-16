from __future__ import annotations

from datetime import datetime, timezone

from geoalchemy2.functions import ST_X, ST_Y
from sqlalchemy.orm import Session

from app.models.activity_point import ActivityPoint
from app.models.activity_quality_metric import ActivityQualityMetric
from app.services.quality import compute_quality

DEFAULT_SPIKE_SPEED_MPS = 12.0
DEFAULT_STOP_SPEED_MPS = 0.6
DEFAULT_STOP_MIN_DURATION_S = 10


def get_persisted_quality_metric(db: Session, activity_id: int) -> ActivityQualityMetric | None:
    return (
        db.query(ActivityQualityMetric)
        .filter(ActivityQualityMetric.activity_id == activity_id)
        .one_or_none()
    )


def upsert_quality_metric_from_series(
    db: Session,
    *,
    activity_id: int,
    latlons: list[tuple[float, float]],
    times: list[int],
    spike_speed_mps: float = DEFAULT_SPIKE_SPEED_MPS,
    stop_speed_mps: float = DEFAULT_STOP_SPEED_MPS,
    stop_min_duration_s: int = DEFAULT_STOP_MIN_DURATION_S,
) -> ActivityQualityMetric:
    report = compute_quality(
        latlons=latlons,
        times=times,
        spike_speed_mps=spike_speed_mps,
        stop_speed_mps=stop_speed_mps,
        stop_min_duration_s=stop_min_duration_s,
    )

    metric = get_persisted_quality_metric(db, activity_id)
    if metric is None:
        metric = ActivityQualityMetric(activity_id=activity_id)
        db.add(metric)

    metric.point_count = report.point_count
    metric.duration_s = report.duration_s
    metric.distance_m_gps = report.distance_m
    metric.max_speed_mps = report.max_speed_mps
    metric.spike_count = report.spike_count
    metric.stopped_time_s = report.stopped_time_s
    metric.stop_segments = report.stop_segments
    metric.jitter_score = report.jitter_score
    metric.spike_speed_threshold_mps = spike_speed_mps
    metric.stop_speed_threshold_mps = stop_speed_mps
    metric.stop_min_duration_s = stop_min_duration_s
    metric.computed_at = datetime.now(timezone.utc)

    return metric


def upsert_quality_metric_from_points(
    db: Session,
    *,
    activity_id: int,
    spike_speed_mps: float = DEFAULT_SPIKE_SPEED_MPS,
    stop_speed_mps: float = DEFAULT_STOP_SPEED_MPS,
    stop_min_duration_s: int = DEFAULT_STOP_MIN_DURATION_S,
) -> ActivityQualityMetric:
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
        raise ValueError("Not enough points. Ingest streams first.")

    latlons = [(float(r[0]), float(r[1])) for r in rows]
    times = [int(r[2]) for r in rows]
    return upsert_quality_metric_from_series(
        db,
        activity_id=activity_id,
        latlons=latlons,
        times=times,
        spike_speed_mps=spike_speed_mps,
        stop_speed_mps=stop_speed_mps,
        stop_min_duration_s=stop_min_duration_s,
    )
