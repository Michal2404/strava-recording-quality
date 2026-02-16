"""Initial schema with PostGIS tables and core constraints."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry

# revision identifiers, used by Alembic.
revision = "20260216_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("strava_athlete_id", sa.BigInteger(), nullable=False),
        sa.Column("firstname", sa.String(length=100), nullable=True),
        sa.Column("lastname", sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_strava_athlete_id", "users", ["strava_athlete_id"], unique=True)

    op.create_table(
        "strava_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("access_token", sa.String(), nullable=False),
        sa.Column("refresh_token", sa.String(), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_strava_tokens_user_id", "strava_tokens", ["user_id"], unique=True)

    op.create_table(
        "activities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("strava_activity_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("sport_type", sa.String(length=50), nullable=True),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("distance_m", sa.Float(), nullable=True),
        sa.Column("moving_time_s", sa.Integer(), nullable=True),
        sa.Column("elevation_gain_m", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_activities_strava_activity_id", "activities", ["strava_activity_id"], unique=True)
    op.create_index("ix_activities_user_id", "activities", ["user_id"], unique=False)

    op.create_table(
        "activity_points",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("activity_id", sa.Integer(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("time_s", sa.Integer(), nullable=False),
        sa.Column("geom", Geometry(geometry_type="POINT", srid=4326, spatial_index=False), nullable=False),
        sa.Column("ele_m", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["activity_id"], ["activities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("activity_id", "seq", name="uq_activity_points_activity_id_seq"),
    )
    op.create_index("ix_activity_points_activity_id", "activity_points", ["activity_id"], unique=False)
    op.create_index(
        "ix_activity_points_geom_gist",
        "activity_points",
        ["geom"],
        unique=False,
        postgresql_using="gist",
    )


def downgrade() -> None:
    op.drop_index("ix_activity_points_geom_gist", table_name="activity_points", postgresql_using="gist")
    op.drop_index("ix_activity_points_activity_id", table_name="activity_points")
    op.drop_table("activity_points")

    op.drop_index("ix_activities_user_id", table_name="activities")
    op.drop_index("ix_activities_strava_activity_id", table_name="activities")
    op.drop_table("activities")

    op.drop_index("ix_strava_tokens_user_id", table_name="strava_tokens")
    op.drop_table("strava_tokens")

    op.drop_index("ix_users_strava_athlete_id", table_name="users")
    op.drop_table("users")
