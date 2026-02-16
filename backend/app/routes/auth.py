from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.models.strava_token import StravaToken
from app.models.user import User

router = APIRouter(prefix="/auth/strava", tags=["auth"])


@router.get("/login")
def strava_login():
    params = {
        "client_id": settings.STRAVA_CLIENT_ID,
        "redirect_uri": settings.STRAVA_REDIRECT_URI,
        "response_type": "code",
        "approval_prompt": "auto",
        "scope": settings.STRAVA_SCOPES,
    }
    return RedirectResponse("https://www.strava.com/oauth/authorize?" + urlencode(params))


@router.get("/callback")
def strava_callback(code: str, scope: str | None = None, db: Session = Depends(get_db)):
    token_url = "https://www.strava.com/oauth/token"
    payload = {
        "client_id": settings.STRAVA_CLIENT_ID,
        "client_secret": settings.STRAVA_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
    }

    try:
        resp = httpx.post(token_url, data=payload, timeout=20.0)
        resp.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {e}")

    data = resp.json()

    athlete = data.get("athlete") or {}
    athlete_id = athlete.get("id")
    if not athlete_id:
        raise HTTPException(status_code=400, detail="No athlete returned by Strava")

    # Upsert user
    user = db.query(User).filter(User.strava_athlete_id == athlete_id).one_or_none()
    if user is None:
        user = User(
            strava_athlete_id=athlete_id,
            firstname=athlete.get("firstname"),
            lastname=athlete.get("lastname"),
        )
        db.add(user)
        db.flush()  # assigns user.id

    # Upsert token (1:1)
    token = db.query(StravaToken).filter(StravaToken.user_id == user.id).one_or_none()
    if token is None:
        token = StravaToken(user_id=user.id)
        db.add(token)

    token.access_token = data["access_token"]
    token.refresh_token = data["refresh_token"]
    token.expires_at = data["expires_at"]

    db.commit()

    redirect_url = settings.AUTH_SUCCESS_REDIRECT_URL or "/"
    return RedirectResponse(url=redirect_url, status_code=303)
