from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.activity import Activity
from app.schemas.activity import ActivityOut

router = APIRouter(prefix="/activities", tags=["activities"])


@router.get("/", response_model=list[ActivityOut])
def list_activities(
    limit: int = 20,
    offset: int = 0,
    sport_type: str | None = None,
    db: Session = Depends(get_db),
):
    """
    List activities, newest first.
    """
    q = db.query(Activity)
    if sport_type:
        q = q.filter(Activity.sport_type.ilike(sport_type))
    q = q.order_by(Activity.start_date.desc().nullslast()).limit(limit).offset(offset)
    return q.all()
