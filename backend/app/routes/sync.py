from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.activity import Activity
from app.models.strava_token import StravaToken
from app.models.user import User
from app.services.strava_session import build_strava_client, persist_refreshed_token

router = APIRouter(prefix="/sync", tags=["sync"])


def parse_start_date(s: str | None):
    if not s:
        return None
    # Strava returns ISO 8601 like "2024-01-01T12:34:56Z"
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def to_unix_timestamp(value: datetime | None) -> int | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return int(value.timestamp())


@router.post("/activities")
def sync_activities(
    db: Session = Depends(get_db),
    per_page: int = Query(30, ge=1, le=200),
    max_pages: int | None = Query(default=None, ge=1, le=5000),
    after: datetime | None = None,
    before: datetime | None = None,
    sport_type: str | None = None,
    name_contains: str | None = None,
):
    if after and before and after >= before:
        raise HTTPException(status_code=400, detail="'after' must be earlier than 'before'")

    # Single-user mode: select the first user.
    user = db.query(User).order_by(User.id.asc()).first()
    if not user:
        raise HTTPException(status_code=404, detail="No user found. Login with Strava first.")

    token = db.query(StravaToken).filter(StravaToken.user_id == user.id).one_or_none()
    if not token:
        raise HTTPException(status_code=404, detail="No Strava token found. Login with Strava first.")

    client = build_strava_client(token)
    after_ts = to_unix_timestamp(after)
    before_ts = to_unix_timestamp(before)
    sport_filter = sport_type.lower() if sport_type else None
    name_filter = name_contains.lower() if name_contains else None

    fetched = 0
    inserted = 0
    updated = 0
    skipped = 0
    pages = 0

    page = 1
    while True:
        if max_pages is not None and page > max_pages:
            break

        items = client.list_activities(
            per_page=per_page,
            page=page,
            after=after_ts,
            before=before_ts,
        )
        if not isinstance(items, list):
            raise HTTPException(status_code=502, detail="Unexpected response from Strava activities API")

        pages += 1
        fetched += len(items)
        if not items:
            break

        for a in items:
            name = a.get("name") or ""
            sport = a.get("sport_type") or a.get("type") or ""

            if sport_filter and sport.lower() != sport_filter:
                skipped += 1
                continue
            if name_filter and name_filter not in name.lower():
                skipped += 1
                continue

            strava_id = a.get("id")
            if strava_id is None:
                skipped += 1
                continue

            activity = db.query(Activity).filter(Activity.strava_activity_id == strava_id).one_or_none()
            if activity is None:
                activity = Activity(strava_activity_id=strava_id, user_id=user.id)
                db.add(activity)
                inserted += 1
            else:
                updated += 1

            activity.name = name or None
            activity.sport_type = sport or None
            activity.start_date = parse_start_date(a.get("start_date"))
            activity.distance_m = a.get("distance")
            activity.moving_time_s = a.get("moving_time")
            activity.elevation_gain_m = a.get("total_elevation_gain")

        if len(items) < per_page:
            break

        page += 1

    persist_refreshed_token(db, token, client, commit=False)
    db.commit()
    upserted = inserted + updated
    return {
        "ok": True,
        "count": upserted,
        "fetched": fetched,
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "pages": pages,
    }
