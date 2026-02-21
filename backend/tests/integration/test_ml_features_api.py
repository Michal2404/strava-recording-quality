from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.activity import Activity
from app.models.activity_ml_feature import ActivityMLFeature
from app.models.activity_quality_metric import ActivityQualityMetric
from app.models.user import User


def _seed_activity(db_session, *, strava_activity_id: int, name: str) -> Activity:
    user = User(
        strava_athlete_id=strava_activity_id + 100_000,
        firstname="ML",
        lastname="Features",
    )
    db_session.add(user)
    db_session.flush()

    activity = Activity(
        strava_activity_id=strava_activity_id,
        user_id=user.id,
        name=name,
        sport_type="Run",
        distance_m=10_000.0,
        moving_time_s=3_600,
        elevation_gain_m=80.0,
    )
    db_session.add(activity)
    db_session.commit()
    db_session.refresh(activity)
    return activity


def _seed_quality_metric(db_session, *, activity_id: int, jitter_score: float = 0.24):
    metric = ActivityQualityMetric(
        activity_id=activity_id,
        point_count=1800,
        duration_s=3600,
        distance_m_gps=9800.0,
        max_speed_mps=5.2,
        spike_count=4,
        stopped_time_s=120,
        stop_segments=3,
        jitter_score=jitter_score,
        spike_speed_threshold_mps=12.0,
        stop_speed_threshold_mps=0.6,
        stop_min_duration_s=10,
        computed_at=datetime.now(timezone.utc),
    )
    db_session.add(metric)
    db_session.commit()


@pytest.mark.integration
def test_activity_features_endpoint_persists_snapshot(api_client, db_session):
    activity = _seed_activity(db_session, strava_activity_id=810001, name="Feature Persist")
    _seed_quality_metric(db_session, activity_id=activity.id)

    response = api_client.get(f"/activities/{activity.id}/features")
    assert response.status_code == 200
    payload = response.json()
    assert payload["activity_id"] == activity.id
    assert payload["feature_version"] == 1
    assert "points_per_km" in payload["features"]
    assert payload["features"]["jitter_score"] == pytest.approx(0.24)

    db_session.expire_all()
    snapshot = (
        db_session.query(ActivityMLFeature)
        .filter(ActivityMLFeature.activity_id == activity.id)
        .one_or_none()
    )
    assert snapshot is not None
    assert snapshot.feature_version == 1
    assert snapshot.features_json["features"]["jitter_score"] == pytest.approx(0.24)


@pytest.mark.integration
def test_activity_features_endpoint_upserts_snapshot(api_client, db_session):
    activity = _seed_activity(db_session, strava_activity_id=810002, name="Feature Upsert")
    _seed_quality_metric(db_session, activity_id=activity.id, jitter_score=0.10)

    first = api_client.get(f"/activities/{activity.id}/features")
    assert first.status_code == 200

    metric = (
        db_session.query(ActivityQualityMetric)
        .filter(ActivityQualityMetric.activity_id == activity.id)
        .one()
    )
    metric.jitter_score = 0.91
    db_session.commit()

    second = api_client.get(f"/activities/{activity.id}/features")
    assert second.status_code == 200
    assert second.json()["features"]["jitter_score"] == pytest.approx(0.91)

    db_session.expire_all()
    snapshots = (
        db_session.query(ActivityMLFeature)
        .filter(ActivityMLFeature.activity_id == activity.id)
        .all()
    )
    assert len(snapshots) == 1
    assert snapshots[0].features_json["features"]["jitter_score"] == pytest.approx(0.91)


@pytest.mark.integration
def test_rebuild_ml_features_defaults_to_labeled_only(api_client, db_session):
    labeled_activity = _seed_activity(db_session, strava_activity_id=810003, name="Labeled")
    unlabeled_activity = _seed_activity(db_session, strava_activity_id=810004, name="Unlabeled")
    _seed_quality_metric(db_session, activity_id=labeled_activity.id)
    _seed_quality_metric(db_session, activity_id=unlabeled_activity.id)

    label_response = api_client.post(
        f"/ml/activities/{labeled_activity.id}/label",
        json={
            "label_bad": True,
            "label_source": "manual",
            "label_reason": "reviewed",
            "label_confidence": 0.8,
        },
    )
    assert label_response.status_code == 200

    rebuild = api_client.post("/ml/features/rebuild")
    assert rebuild.status_code == 200
    data = rebuild.json()
    assert data["labeled_only"] is True
    assert data["selected"] == 1
    assert data["rebuilt"] == 1
    assert data["skipped"] == 0

    db_session.expire_all()
    snapshots = db_session.query(ActivityMLFeature).all()
    assert len(snapshots) == 1
    assert snapshots[0].activity_id == labeled_activity.id


@pytest.mark.integration
def test_rebuild_ml_features_supports_all_activities_and_skips_missing_data(api_client, db_session):
    with_metric = _seed_activity(db_session, strava_activity_id=810005, name="With metric")
    without_metric = _seed_activity(db_session, strava_activity_id=810006, name="Without metric")
    _seed_quality_metric(db_session, activity_id=with_metric.id)

    rebuild = api_client.post("/ml/features/rebuild?labeled_only=false")
    assert rebuild.status_code == 200
    data = rebuild.json()
    assert data["labeled_only"] is False
    assert data["selected"] == 2
    assert data["rebuilt"] == 1
    assert data["skipped"] == 1
    assert without_metric.id in data["skipped_activity_ids"]

    db_session.expire_all()
    snapshots = db_session.query(ActivityMLFeature).all()
    assert len(snapshots) == 1
    assert snapshots[0].activity_id == with_metric.id
