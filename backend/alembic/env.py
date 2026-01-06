"""
Alembic environment configuration.

This env.py is configured to:
- Load DATABASE_URL from app.core.config.settings
- Use SQLAlchemy model metadata for autogenerate
- IGNORE PostGIS / extension-managed tables (e.g., spatial_ref_sys, tiger geocoder)
  so Alembic won't try to drop them.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.models import Base  # imports all models and registers them on Base.metadata

# Alembic Config object, provides access to values within alembic.ini
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Model metadata for 'autogenerate' support
target_metadata = Base.metadata


def include_object(object_, name, type_, reflected, compare_to):
    """
    Only include tables that are part of our SQLAlchemy metadata.

    This prevents Alembic autogenerate from trying to drop tables that exist in the
    database but are managed by PostGIS / extensions (e.g., spatial_ref_sys,
    postgis_tiger_geocoder tables, topology tables, etc.).
    """
    if type_ == "table":
        return name in target_metadata.tables
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (no DB connection)."""
    url = settings.DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (with DB connection)."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = settings.DATABASE_URL

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
