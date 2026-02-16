from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.strava import StravaClient
from app.models.strava_token import StravaToken


def build_strava_client(token: StravaToken) -> StravaClient:
    return StravaClient(
        access_token=token.access_token,
        refresh_token=token.refresh_token,
        expires_at=token.expires_at,
        client_id=settings.STRAVA_CLIENT_ID,
        client_secret=settings.STRAVA_CLIENT_SECRET,
    )


def persist_refreshed_token(
    db: Session,
    token: StravaToken,
    client: StravaClient,
    *,
    commit: bool = False,
) -> bool:
    if not client.token_was_refreshed:
        return False

    token.access_token = client.access_token
    if client.refresh_token:
        token.refresh_token = client.refresh_token
    if client.expires_at is not None:
        token.expires_at = client.expires_at
    db.add(token)

    if commit:
        db.commit()
        db.refresh(token)

    return True
