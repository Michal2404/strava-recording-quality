"""Add persisted activity ML feature snapshot table."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260220_0004"
down_revision = "20260219_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "activity_ml_features",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("activity_id", sa.Integer(), nullable=False),
        sa.Column("feature_version", sa.Integer(), nullable=False),
        sa.Column("features_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["activity_id"], ["activities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("activity_id", name="uq_activity_ml_features_activity_id"),
    )
    op.create_index(
        "ix_activity_ml_features_feature_version",
        "activity_ml_features",
        ["feature_version"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_activity_ml_features_feature_version", table_name="activity_ml_features")
    op.drop_table("activity_ml_features")
