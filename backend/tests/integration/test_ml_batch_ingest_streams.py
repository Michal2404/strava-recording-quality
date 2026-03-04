from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.ml.batch_ingest_streams import backfill_activity_streams
from app.models.activity import Activity
from app.models.activity_quality_metric import ActivityQualityMetric
from app.models.user import User
from app.services.stream_ingest import MissingStreamDataError


def _seed_user(db_session, *, athlete_id: int) -> User:
    user = User(
        strava_athlete_id=athlete_id,
        firstname="Batch",
        lastname="Ingest",
    )
    db_session.add(user)
    db_session.flush()
    return user


def _seed_activity(
    db_session,
    *,
    user_id: int,
    strava_activity_id: int,
    start_date: datetime,
    sport_type: str,
) -> Activity:
    activity = Activity(
        strava_activity_id=strava_activity_id,
        user_id=user_id,
        name=f"Activity-{strava_activity_id}",
        sport_type=sport_type,
        start_date=start_date,
        distance_m=10_000.0,
    )
    db_session.add(activity)
    db_session.flush()
    return activity


def _seed_metric(db_session, *, activity_id: int) -> None:
    db_session.add(
        ActivityQualityMetric(
            activity_id=activity_id,
            point_count=1000,
            duration_s=3600,
            distance_m_gps=10_100.0,
            max_speed_mps=6.0,
            spike_count=2,
            stopped_time_s=100,
            stop_segments=1,
            jitter_score=0.1,
            spike_speed_threshold_mps=12.0,
            stop_speed_threshold_mps=0.6,
            stop_min_duration_s=10,
            computed_at=datetime.now(timezone.utc),
        )
    )


@pytest.mark.integration
def test_backfill_activity_streams_selects_missing_metrics_and_tracks_errors(db_session, monkeypatch, tmp_path):
    user = _seed_user(db_session, athlete_id=940001)

    a1 = _seed_activity(
        db_session,
        user_id=user.id,
        strava_activity_id=950001,
        start_date=datetime(2024, 1, 3, tzinfo=timezone.utc),
        sport_type="Run",
    )
    a2 = _seed_activity(
        db_session,
        user_id=user.id,
        strava_activity_id=950002,
        start_date=datetime(2024, 1, 2, tzinfo=timezone.utc),
        sport_type="Run",
    )
    a3 = _seed_activity(
        db_session,
        user_id=user.id,
        strava_activity_id=950003,
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        sport_type="Ride",
    )
    _seed_metric(db_session, activity_id=a3.id)
    db_session.commit()

    calls: list[int] = []

    def fake_ingest(db, *, activity_id: int, commit: bool = True):
        calls.append(activity_id)
        if activity_id == a2.id:
            raise MissingStreamDataError("Missing latlng or time streams")
        return SimpleNamespace(activity_id=activity_id, points=123)

    monkeypatch.setattr("app.ml.batch_ingest_streams.ingest_streams_for_activity", fake_ingest)

    summary = backfill_activity_streams(
        db_session,
        only_missing_metrics=True,
        sport_type="Run",
        after=datetime(2024, 1, 1, tzinfo=timezone.utc),
        before=datetime(2024, 1, 31, tzinfo=timezone.utc),
        output_path=tmp_path / "ingest_summary.json",
    )

    assert set(calls) == {a1.id, a2.id}
    assert summary["selected_activities"] == 2
    assert summary["ingested"] == 1
    assert summary["missing_stream_data"] == 1
    assert summary["failed"] == 0
    assert summary["total_points_written"] == 123
    assert summary["summary_path"].endswith("ingest_summary.json")

