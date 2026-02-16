from __future__ import annotations

import json
from pathlib import Path

import pytest

import app.routes.streams as streams_route
from app.models.activity import Activity
from app.models.activity_point import ActivityPoint
from app.models.activity_quality_metric import ActivityQualityMetric
from app.models.strava_token import StravaToken
from app.models.user import User


class FakeStravaClient:
    def __init__(self, streams_payload: dict):
        self._streams_payload = streams_payload

    def get_activity_streams(self, activity_id: int):
        return self._streams_payload


def _fixture_streams_payload() -> dict:
    fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "streams_small_run.json"
    with fixture_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _seed_activity(db_session) -> Activity:
    user = User(
        strava_athlete_id=123456,
        firstname="Test",
        lastname="Runner",
    )
    db_session.add(user)
    db_session.flush()

    token = StravaToken(
        user_id=user.id,
        access_token="access-token",
        refresh_token="refresh-token",
        expires_at=2_147_483_000,
    )
    db_session.add(token)

    activity = Activity(
        strava_activity_id=999111,
        user_id=user.id,
        name="Fixture Run",
        sport_type="Run",
    )
    db_session.add(activity)
    db_session.commit()
    db_session.refresh(activity)
    return activity


def _ingest_for_activity(api_client, activity_id: int):
    response = api_client.post(f"/activities/{activity_id}/ingest_streams")
    assert response.status_code == 200
    return response


@pytest.mark.integration
def test_ingest_streams_persists_points_and_quality_metrics(api_client, db_session, monkeypatch):
    activity = _seed_activity(db_session)
    streams_payload = _fixture_streams_payload()

    monkeypatch.setattr(
        streams_route,
        "build_strava_client",
        lambda token: FakeStravaClient(streams_payload),
    )
    monkeypatch.setattr(
        streams_route,
        "persist_refreshed_token",
        lambda *args, **kwargs: False,
    )

    response = _ingest_for_activity(api_client, activity.id)
    assert response.json()["points"] == len(streams_payload["latlng"]["data"])

    db_session.expire_all()
    point_count = (
        db_session.query(ActivityPoint)
        .filter(ActivityPoint.activity_id == activity.id)
        .count()
    )
    metric = (
        db_session.query(ActivityQualityMetric)
        .filter(ActivityQualityMetric.activity_id == activity.id)
        .one_or_none()
    )
    assert point_count == 3
    assert metric is not None
    assert metric.point_count == 3
    assert metric.computed_at is not None


@pytest.mark.integration
def test_track_endpoint_returns_geojson_linestring(api_client, db_session, monkeypatch):
    activity = _seed_activity(db_session)
    streams_payload = _fixture_streams_payload()

    monkeypatch.setattr(
        streams_route,
        "build_strava_client",
        lambda token: FakeStravaClient(streams_payload),
    )
    monkeypatch.setattr(
        streams_route,
        "persist_refreshed_token",
        lambda *args, **kwargs: False,
    )

    _ingest_for_activity(api_client, activity.id)
    response = api_client.get(f"/activities/{activity.id}/track")
    assert response.status_code == 200

    payload = response.json()
    assert payload["type"] == "Feature"
    assert payload["geometry"]["type"] == "LineString"
    assert len(payload["geometry"]["coordinates"]) == 3


@pytest.mark.integration
def test_quality_endpoint_uses_persisted_metrics_when_points_are_missing(
    api_client,
    db_session,
    monkeypatch,
):
    activity = _seed_activity(db_session)
    streams_payload = _fixture_streams_payload()

    monkeypatch.setattr(
        streams_route,
        "build_strava_client",
        lambda token: FakeStravaClient(streams_payload),
    )
    monkeypatch.setattr(
        streams_route,
        "persist_refreshed_token",
        lambda *args, **kwargs: False,
    )

    _ingest_for_activity(api_client, activity.id)

    db_session.query(ActivityPoint).filter(ActivityPoint.activity_id == activity.id).delete()
    db_session.commit()
    db_session.expire_all()

    response = api_client.get(f"/activities/{activity.id}/quality")
    assert response.status_code == 200

    payload = response.json()
    assert payload["activity_id"] == activity.id
    assert payload["point_count"] == 3
    assert payload["computed_at"] is not None
