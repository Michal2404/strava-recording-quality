from __future__ import annotations

from urllib.parse import parse_qs, urlparse

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


def _complete_login(api_client, monkeypatch, *, success_redirect: str = "/"):
    def fake_post(url: str, data: dict, timeout: float):
        assert url == "https://www.strava.com/oauth/token"
        assert data["code"] == "fake-code"
        return _FakeTokenResponse()

    monkeypatch.setattr(auth_route.httpx, "post", fake_post)
    monkeypatch.setattr(auth_route.settings, "AUTH_SUCCESS_REDIRECT_URL", success_redirect)

    login_response = api_client.get("/auth/strava/login", follow_redirects=False)
    assert login_response.status_code == 303

    location = login_response.headers["location"]
    state = parse_qs(urlparse(location).query)["state"][0]

    callback_response = api_client.get(
        f"/auth/strava/callback?code=fake-code&state={state}",
        follow_redirects=False,
    )
    return callback_response


@pytest.mark.integration
def test_strava_callback_redirects_and_persists_token(api_client, db_session, monkeypatch):
    response = _complete_login(api_client, monkeypatch)

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


@pytest.mark.integration
def test_me_requires_authenticated_session(api_client):
    response = api_client.get("/auth/strava/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


@pytest.mark.integration
def test_login_flow_establishes_browser_session(api_client, monkeypatch):
    callback_response = _complete_login(api_client, monkeypatch, success_redirect="/dashboard")

    assert callback_response.status_code == 303
    assert callback_response.headers["location"] == "/dashboard"

    me_response = api_client.get("/auth/strava/me")
    assert me_response.status_code == 200
    assert me_response.json() == {
        "id": 1,
        "strava_athlete_id": 106491649,
        "firstname": "Michal",
        "lastname": "Tester",
    }
