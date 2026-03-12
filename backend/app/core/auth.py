from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.activity import Activity
from app.models.user import User

SESSION_USER_ID_KEY = "user_id"


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    user_id = request.session.get(SESSION_USER_ID_KEY)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    user = db.query(User).filter(User.id == user_id).one_or_none()
    if user is None:
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    return user


def get_user_activity_or_404(
    db: Session,
    *,
    current_user: User,
    activity_id: int,
) -> Activity:
    activity = (
        db.query(Activity)
        .filter(Activity.id == activity_id, Activity.user_id == current_user.id)
        .one_or_none()
    )
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    return activity
