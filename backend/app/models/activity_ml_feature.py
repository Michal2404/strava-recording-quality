from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ActivityMLFeature(Base):
    __tablename__ = "activity_ml_features"

    id: Mapped[int] = mapped_column(primary_key=True)

    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"),
        unique=True,
    )
    activity = relationship("Activity")

    feature_version: Mapped[int] = mapped_column(Integer, nullable=False)
    features_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
