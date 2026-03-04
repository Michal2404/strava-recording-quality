from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.ml.bootstrap_labels import (
    BAD_REASON_SPIKES,
    GOOD_REASON_BASELINE,
    WEAK_LABEL_SOURCE,
    bootstrap_weak_labels,
)
from app.models.activity import Activity
from app.models.activity_quality_label import ActivityQualityLabel
from app.models.activity_quality_metric import ActivityQualityMetric
from app.models.user import User


def _seed_user(db_session, *, athlete_id: int) -> User:
    user = User(
        strava_athlete_id=athlete_id,
        firstname="ML",
        lastname="Bootstrap",
    )
    db_session.add(user)
    db_session.flush()
    return user


def _seed_activity(
    db_session,
    *,
    user_id: int,
    strava_activity_id: int,
    distance_m: float | None,
    name: str,
) -> Activity:
    activity = Activity(
        strava_activity_id=strava_activity_id,
        user_id=user_id,
        name=name,
        sport_type="Run",
        distance_m=distance_m,
    )
    db_session.add(activity)
    db_session.flush()
    return activity


def _seed_metric(
    db_session,
    *,
    activity_id: int,
    distance_m_gps: float,
    spike_count: int,
    jitter_score: float,
    max_speed_mps: float,
) -> None:
    metric = ActivityQualityMetric(
        activity_id=activity_id,
        point_count=1200,
        duration_s=3600,
        distance_m_gps=distance_m_gps,
        max_speed_mps=max_speed_mps,
        spike_count=spike_count,
        stopped_time_s=150,
        stop_segments=2,
        jitter_score=jitter_score,
        spike_speed_threshold_mps=12.0,
        stop_speed_threshold_mps=0.6,
        stop_min_duration_s=10,
        computed_at=datetime.now(timezone.utc),
    )
    db_session.add(metric)


@pytest.mark.integration
def test_bootstrap_weak_labels_backfills_and_preserves_manual_labels(db_session, tmp_path):
    user = _seed_user(db_session, athlete_id=910001)

    good_activity = _seed_activity(
        db_session,
        user_id=user.id,
        strava_activity_id=920001,
        distance_m=10_000.0,
        name="Good",
    )
    bad_activity = _seed_activity(
        db_session,
        user_id=user.id,
        strava_activity_id=920002,
        distance_m=10_000.0,
        name="Bad",
    )
    manual_activity = _seed_activity(
        db_session,
        user_id=user.id,
        strava_activity_id=920003,
        distance_m=10_000.0,
        name="Manual Protected",
    )
    _seed_activity(
        db_session,
        user_id=user.id,
        strava_activity_id=920004,
        distance_m=10_000.0,
        name="No Metric",
    )
    weak_existing_activity = _seed_activity(
        db_session,
        user_id=user.id,
        strava_activity_id=920005,
        distance_m=10_000.0,
        name="Existing Weak",
    )

    _seed_metric(
        db_session,
        activity_id=good_activity.id,
        distance_m_gps=9_900.0,
        spike_count=3,
        jitter_score=0.10,
        max_speed_mps=5.6,
    )
    _seed_metric(
        db_session,
        activity_id=bad_activity.id,
        distance_m_gps=9_500.0,
        spike_count=120,
        jitter_score=0.15,
        max_speed_mps=6.0,
    )
    _seed_metric(
        db_session,
        activity_id=manual_activity.id,
        distance_m_gps=10_100.0,
        spike_count=6,
        jitter_score=0.10,
        max_speed_mps=5.5,
    )
    _seed_metric(
        db_session,
        activity_id=weak_existing_activity.id,
        distance_m_gps=9_800.0,
        spike_count=4,
        jitter_score=0.10,
        max_speed_mps=5.7,
    )

    db_session.add(
        ActivityQualityLabel(
            activity_id=manual_activity.id,
            label_bad=True,
            label_source="manual",
            label_reason="human_review",
            label_confidence=1.0,
            label_version=1,
            created_by="reviewer",
        )
    )
    db_session.add(
        ActivityQualityLabel(
            activity_id=weak_existing_activity.id,
            label_bad=True,
            label_source=WEAK_LABEL_SOURCE,
            label_reason="old_reason",
            label_confidence=0.7,
            label_version=1,
            created_by="old-bootstrap",
        )
    )
    db_session.commit()

    summary_path = tmp_path / "bootstrap_summary.json"
    summary = bootstrap_weak_labels(
        db_session,
        created_by="test-bootstrap",
        output_path=summary_path,
    )

    assert summary["selected_activities"] == 5
    assert summary["processed_with_metrics"] == 4
    assert summary["created"] == 2
    assert summary["updated"] == 1
    assert summary["skipped_manual"] == 1
    assert summary["skipped_missing_metric"] == 1
    assert summary["class_balance"]["total"] == 3

    labels = (
        db_session.query(ActivityQualityLabel)
        .order_by(ActivityQualityLabel.activity_id.asc())
        .all()
    )
    assert len(labels) == 4

    by_activity = {row.activity_id: row for row in labels}

    assert by_activity[good_activity.id].label_source == WEAK_LABEL_SOURCE
    assert by_activity[good_activity.id].label_bad is False
    assert by_activity[good_activity.id].label_reason == GOOD_REASON_BASELINE
    assert by_activity[good_activity.id].created_by == "test-bootstrap"

    assert by_activity[bad_activity.id].label_source == WEAK_LABEL_SOURCE
    assert by_activity[bad_activity.id].label_bad is True
    assert BAD_REASON_SPIKES in by_activity[bad_activity.id].label_reason

    assert by_activity[manual_activity.id].label_source == "manual"
    assert by_activity[manual_activity.id].label_reason == "human_review"
    assert by_activity[manual_activity.id].created_by == "reviewer"

    assert by_activity[weak_existing_activity.id].label_source == WEAK_LABEL_SOURCE
    assert by_activity[weak_existing_activity.id].label_bad is False
    assert by_activity[weak_existing_activity.id].created_by == "test-bootstrap"

    assert summary_path.exists()
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["selected_activities"] == 5
    assert payload["class_balance"]["total"] == 3
