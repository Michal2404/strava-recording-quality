from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geometry

from app.models.base import Base


class ActivityPoint(Base):
    __tablename__ = "activity_points"
    __table_args__ = (
        UniqueConstraint("activity_id", "seq", name="uq_activity_points_activity_id_seq"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"),
        index=True,
    )
    activity = relationship("Activity")

    # index of the point in the stream (0, 1, 2, ...)
    seq: Mapped[int] = mapped_column(Integer)

    # seconds since activity start
    time_s: Mapped[int] = mapped_column(Integer)

    # raw geometry (lon/lat)
    geom: Mapped[str] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True)
    )

    # optional elevation (meters)
    ele_m: Mapped[int | None] = mapped_column(Integer, nullable=True)
