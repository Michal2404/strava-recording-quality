from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Provide safe defaults so test imports do not require a local .env with secrets.
os.environ.setdefault("STRAVA_CLIENT_ID", "test-client-id")
os.environ.setdefault("STRAVA_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("STRAVA_REDIRECT_URI", "http://127.0.0.1:8000/auth/strava/callback")
os.environ.setdefault("STRAVA_SCOPES", "read,activity:read_all")

from app.core.db import get_db
from app.main import app

DEFAULT_TEST_DATABASE_URL = "postgresql+psycopg://app:app@localhost:5432/livemap_test"


def _ensure_database_exists(database_url: str) -> None:
    parsed = make_url(database_url)
    database_name = parsed.database
    if not database_name:
        raise RuntimeError("TEST_DATABASE_URL must include a database name")
    if not re.fullmatch(r"[A-Za-z0-9_]+", database_name):
        raise RuntimeError("TEST_DATABASE_URL database name must be alphanumeric with underscores")

    admin_url = parsed.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT", future=True)
    try:
        with admin_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :database_name"),
                {"database_name": database_name},
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{database_name}"'))
    finally:
        admin_engine.dispose()


def _run_migrations(database_url: str) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    env["PYTHONPATH"] = "."
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def _truncate_tables(db: Session) -> None:
    db.execute(
        text(
            """
            TRUNCATE TABLE
              activity_quality_metrics,
              activity_points,
              activities,
              strava_tokens,
              users
            RESTART IDENTITY CASCADE
            """
        )
    )
    db.commit()


@pytest.fixture(scope="session")
def integration_db_url() -> str:
    return os.getenv("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)


@pytest.fixture(scope="session")
def integration_engine(integration_db_url: str) -> Generator[Engine, None, None]:
    try:
        _ensure_database_exists(integration_db_url)
        _run_migrations(integration_db_url)
        engine = create_engine(integration_db_url, pool_pre_ping=True, future=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"Integration database unavailable: {exc}")

    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def session_factory(integration_engine: Engine):
    return sessionmaker(bind=integration_engine, autoflush=False, autocommit=False)


@pytest.fixture()
def clean_database(session_factory):
    with session_factory() as db:
        _truncate_tables(db)

    yield

    with session_factory() as db:
        _truncate_tables(db)


@pytest.fixture()
def db_session(session_factory, clean_database) -> Generator[Session, None, None]:
    with session_factory() as db:
        yield db


@pytest.fixture()
def api_client(session_factory, clean_database) -> Generator[TestClient, None, None]:
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
