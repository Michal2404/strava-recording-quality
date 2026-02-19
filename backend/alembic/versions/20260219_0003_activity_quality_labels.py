"""Add activity quality labels table for ML supervision."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260219_0003"
down_revision = "20260216_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "activity_quality_labels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("activity_id", sa.Integer(), nullable=False),
        sa.Column("label_bad", sa.Boolean(), nullable=False),
        sa.Column("label_source", sa.String(length=32), nullable=False),
        sa.Column("label_reason", sa.Text(), nullable=True),
        sa.Column("label_confidence", sa.Float(), nullable=True),
        sa.Column("label_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(["activity_id"], ["activities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("activity_id", name="uq_activity_quality_labels_activity_id"),
    )
    op.create_index(
        "ix_activity_quality_labels_label_source",
        "activity_quality_labels",
        ["label_source"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_activity_quality_labels_label_source", table_name="activity_quality_labels")
    op.drop_table("activity_quality_labels")
