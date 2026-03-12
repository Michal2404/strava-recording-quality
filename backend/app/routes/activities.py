from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.db import get_db
from app.models.activity import Activity
from app.models.user import User
from app.schemas.activity import ActivityOut

router = APIRouter(prefix="/activities", tags=["activities"])


@router.get("/", response_model=list[ActivityOut])
def list_activities(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    sport_type: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List activities, newest first.
    """
    q = db.query(Activity).filter(Activity.user_id == current_user.id)
    if sport_type:
        q = q.filter(Activity.sport_type.ilike(sport_type))
    q = q.order_by(Activity.start_date.desc().nullslast())
    if limit is not None:
        q = q.limit(limit)
    q = q.offset(offset)
    return q.all()
