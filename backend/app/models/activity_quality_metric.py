from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ActivityQualityMetric(Base):
    __tablename__ = "activity_quality_metrics"

    id: Mapped[int] = mapped_column(primary_key=True)

    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    activity = relationship("Activity")

    point_count: Mapped[int] = mapped_column(Integer)
    duration_s: Mapped[int] = mapped_column(Integer)
    distance_m_gps: Mapped[float] = mapped_column(Float)
    max_speed_mps: Mapped[float] = mapped_column(Float)
    spike_count: Mapped[int] = mapped_column(Integer)
    stopped_time_s: Mapped[int] = mapped_column(Integer)
    stop_segments: Mapped[int] = mapped_column(Integer)
    jitter_score: Mapped[float] = mapped_column(Float)

    spike_speed_threshold_mps: Mapped[float] = mapped_column(Float)
    stop_speed_threshold_mps: Mapped[float] = mapped_column(Float)
    stop_min_duration_s: Mapped[int] = mapped_column(Integer)

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
