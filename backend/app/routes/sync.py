from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.integrations.strava import StravaClient
from app.models.activity import Activity
from app.models.strava_token import StravaToken
from app.models.user import User

router = APIRouter(prefix="/sync", tags=["sync"])


def parse_start_date(s: str | None):
    if not s:
        return None
    # Strava returns ISO 8601 like "2024-01-01T12:34:56Z"
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


@router.post("/activities")
def sync_activities(
    db: Session = Depends(get_db),
    per_page: int = 30,
    sport_type: str | None = None,
    name_contains: str | None = None,
):
    # Since you have only one user right now, we just take the first user.
    # Later we’ll do proper auth/session.
    user = db.query(User).order_by(User.id.asc()).first()
    if not user:
        raise HTTPException(status_code=404, detail="No user found. Login with Strava first.")

    token = db.query(StravaToken).filter(StravaToken.user_id == user.id).one_or_none()
    if not token:
        raise HTTPException(status_code=404, detail="No Strava token found. Login with Strava first.")

    client = StravaClient(token.access_token)
    items = client.list_activities(per_page=per_page, page=1)

    upserted = 0
    sport_filter = sport_type.lower() if sport_type else None
    name_filter = name_contains.lower() if name_contains else None

    for a in items:
        name = a.get("name") or ""
        sport = a.get("sport_type") or a.get("type") or ""

        if sport_filter and sport.lower() != sport_filter:
            continue
        if name_filter and name_filter not in name.lower():
            continue

        strava_id = a["id"]

        activity = db.query(Activity).filter(Activity.strava_activity_id == strava_id).one_or_none()
        if activity is None:
            activity = Activity(strava_activity_id=strava_id, user_id=user.id)
            db.add(activity)

        activity.name = name or None
        activity.sport_type = sport or None
        activity.start_date = parse_start_date(a.get("start_date"))
        activity.distance_m = a.get("distance")
        activity.moving_time_s = a.get("moving_time")
        activity.elevation_gain_m = a.get("total_elevation_gain")

        upserted += 1

    db.commit()
    return {"ok": True, "count": upserted}
