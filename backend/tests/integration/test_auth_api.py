from __future__ import annotations

import pytest

import app.routes.auth as auth_route
from app.models.strava_token import StravaToken
from app.models.user import User


class _FakeTokenResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "access_token": "access-token-1",
            "refresh_token": "refresh-token-1",
            "expires_at": 2_147_483_000,
            "athlete": {
                "id": 106491649,
                "firstname": "Michal",
                "lastname": "Tester",
            },
        }


@pytest.mark.integration
def test_strava_callback_redirects_and_persists_token(api_client, db_session, monkeypatch):
    def fake_post(url: str, data: dict, timeout: float):
        assert url == "https://www.strava.com/oauth/token"
        assert data["code"] == "fake-code"
        return _FakeTokenResponse()

    monkeypatch.setattr(auth_route.httpx, "post", fake_post)
    monkeypatch.setattr(auth_route.settings, "AUTH_SUCCESS_REDIRECT_URL", "/")

    response = api_client.get(
        "/auth/strava/callback?code=fake-code",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/"

    user = db_session.query(User).filter(User.strava_athlete_id == 106491649).one_or_none()
    assert user is not None

    token = (
        db_session.query(StravaToken)
        .filter(StravaToken.user_id == user.id)
        .one_or_none()
    )
    assert token is not None
    assert token.access_token == "access-token-1"
    assert token.refresh_token == "refresh-token-1"
