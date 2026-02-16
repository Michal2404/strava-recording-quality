"""Add persisted activity quality metrics table."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260216_0002"
down_revision = "20260216_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "activity_quality_metrics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("activity_id", sa.Integer(), nullable=False),
        sa.Column("point_count", sa.Integer(), nullable=False),
        sa.Column("duration_s", sa.Integer(), nullable=False),
        sa.Column("distance_m_gps", sa.Float(), nullable=False),
        sa.Column("max_speed_mps", sa.Float(), nullable=False),
        sa.Column("spike_count", sa.Integer(), nullable=False),
        sa.Column("stopped_time_s", sa.Integer(), nullable=False),
        sa.Column("stop_segments", sa.Integer(), nullable=False),
        sa.Column("jitter_score", sa.Float(), nullable=False),
        sa.Column("spike_speed_threshold_mps", sa.Float(), nullable=False),
        sa.Column("stop_speed_threshold_mps", sa.Float(), nullable=False),
        sa.Column("stop_min_duration_s", sa.Integer(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["activity_id"], ["activities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_activity_quality_metrics_activity_id",
        "activity_quality_metrics",
        ["activity_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_activity_quality_metrics_activity_id", table_name="activity_quality_metrics")
    op.drop_table("activity_quality_metrics")
