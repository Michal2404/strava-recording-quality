from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.observability import setup_observability
from app.main import app


def test_health_sets_request_id_header() -> None:
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers.get("x-request-id")


def test_request_id_is_forwarded_from_header() -> None:
    client = TestClient(app)
    response = client.get("/health", headers={"X-Request-ID": "req-123"})

    assert response.status_code == 200
    assert response.headers.get("x-request-id") == "req-123"


def test_unhandled_exception_returns_request_id() -> None:
    test_app = FastAPI()
    setup_observability(test_app, settings)

    @test_app.get("/boom")
    def boom():
        raise RuntimeError("kaboom")

    client = TestClient(test_app)
    response = client.get("/boom", headers={"X-Request-ID": "req-boom"})

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error", "request_id": "req-boom"}
    assert response.headers.get("x-request-id") == "req-boom"
