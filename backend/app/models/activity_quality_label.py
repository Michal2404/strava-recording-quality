from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ActivityQualityLabel(Base):
    __tablename__ = "activity_quality_labels"

    id: Mapped[int] = mapped_column(primary_key=True)

    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"),
        unique=True,
    )
    activity = relationship("Activity")

    label_bad: Mapped[bool] = mapped_column(Boolean, nullable=False)
    label_source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    label_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    label_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    label_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
