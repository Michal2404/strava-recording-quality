from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.activity import Activity
from app.models.activity_quality_label import ActivityQualityLabel
from app.schemas.ml_label import ActivityQualityLabelOut, ActivityQualityLabelUpsertIn

router = APIRouter(prefix="/ml", tags=["ml"])

ALLOWED_LABEL_SOURCES = {"manual", "weak_rule"}


@router.post("/activities/{activity_id}/label", response_model=ActivityQualityLabelOut)
def upsert_activity_label(
    activity_id: int,
    payload: ActivityQualityLabelUpsertIn,
    db: Session = Depends(get_db),
):
    activity = db.query(Activity).filter(Activity.id == activity_id).one_or_none()
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")

    if payload.label_source not in ALLOWED_LABEL_SOURCES:
        allowed = ", ".join(sorted(ALLOWED_LABEL_SOURCES))
        raise HTTPException(status_code=400, detail=f"label_source must be one of: {allowed}")

    label = (
        db.query(ActivityQualityLabel)
        .filter(ActivityQualityLabel.activity_id == activity_id)
        .one_or_none()
    )
    if label is None:
        label = ActivityQualityLabel(activity_id=activity_id)
        db.add(label)

    label.label_bad = payload.label_bad
    label.label_source = payload.label_source
    label.label_reason = payload.label_reason
    label.label_confidence = payload.label_confidence
    label.label_version = payload.label_version
    label.created_by = payload.created_by

    db.commit()
    db.refresh(label)
    return label


@router.get("/labels", response_model=list[ActivityQualityLabelOut])
def list_labels(
    label_bad: bool | None = None,
    label_source: str | None = None,
    activity_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    q = db.query(ActivityQualityLabel)
    if label_bad is not None:
        q = q.filter(ActivityQualityLabel.label_bad == label_bad)
    if label_source is not None:
        q = q.filter(ActivityQualityLabel.label_source == label_source)
    if activity_id is not None:
        q = q.filter(ActivityQualityLabel.activity_id == activity_id)

    return (
        q.order_by(ActivityQualityLabel.created_at.desc(), ActivityQualityLabel.id.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
