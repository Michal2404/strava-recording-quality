from __future__ import annotations

import pytest

import app.routes.sync as sync_route
from app.models.activity import Activity
from app.models.strava_token import StravaToken
from app.models.user import User


class _FakeStravaClient:
    def __init__(self, payloads: list[list[dict]]):
        self._payloads = payloads
        self._index = 0

    def list_activities(self, **kwargs):
        payload = self._payloads[self._index]
        if self._index < len(self._payloads) - 1:
            self._index += 1
        return payload


def _seed_user_with_token(
    db_session,
    *,
    athlete_id: int,
    access_token: str,
) -> User:
    user = User(
        strava_athlete_id=athlete_id,
        firstname="Sync",
        lastname="User",
    )
    db_session.add(user)
    db_session.flush()

    db_session.add(
        StravaToken(
            user_id=user.id,
            access_token=access_token,
            refresh_token=f"{access_token}-refresh",
            expires_at=2_147_483_000,
        )
    )
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.mark.integration
def test_sync_activities_uses_authenticated_users_token(
    api_client,
    db_session,
    monkeypatch,
    authenticate_as,
):
    first_user = _seed_user_with_token(
        db_session,
        athlete_id=900001,
        access_token="access-token-1",
    )
    current_user = _seed_user_with_token(
        db_session,
        athlete_id=900002,
        access_token="access-token-2",
    )
    authenticate_as(current_user.id)

    captured_access_tokens: list[str] = []

    def fake_build_strava_client(token):
        captured_access_tokens.append(token.access_token)
        return _FakeStravaClient(
            [
                [
                    {
                        "id": 123456789,
                        "name": "Private Session Run",
                        "sport_type": "Run",
                        "start_date": "2026-03-10T18:45:00Z",
                        "distance": 10234.0,
                        "moving_time": 2810,
                        "total_elevation_gain": 121.0,
                    }
                ],
                [],
            ]
        )

    monkeypatch.setattr(sync_route, "build_strava_client", fake_build_strava_client)
    monkeypatch.setattr(sync_route, "persist_refreshed_token", lambda *args, **kwargs: None)

    response = api_client.post("/sync/activities")

    assert response.status_code == 200
    assert captured_access_tokens == ["access-token-2"]

    activities = db_session.query(Activity).all()
    assert len(activities) == 1
    assert activities[0].user_id == current_user.id
    assert activities[0].user_id != first_user.id
