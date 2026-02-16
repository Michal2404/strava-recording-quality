from __future__ import annotations

import logging
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.config import Settings

request_logger = logging.getLogger("app.request")
error_logger = logging.getLogger("app.error")


def _init_sentry(settings: Settings) -> None:
    if not settings.SENTRY_DSN:
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
    except ImportError:
        error_logger.warning(
            "SENTRY_DSN configured but sentry_sdk is not installed; skipping Sentry init"
        )
        return

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        integrations=[FastApiIntegration()],
    )
    request_logger.info(
        "Sentry initialized",
        extra={"sentry_traces_sample_rate": settings.SENTRY_TRACES_SAMPLE_RATE},
    )


def setup_observability(app: FastAPI, settings: Settings) -> None:
    _init_sentry(settings)

    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid4())
        start = perf_counter()
        client_host = request.client.host if request.client else None

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((perf_counter() - start) * 1000, 2)
            error_logger.exception(
                "Unhandled request exception",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "query": request.url.query,
                    "client_ip": client_host,
                    "duration_ms": duration_ms,
                },
            )
            response = JSONResponse(
                status_code=500,
                content={"detail": "Internal server error", "request_id": request_id},
            )

        duration_ms = round((perf_counter() - start) * 1000, 2)
        request_logger.info(
            "Request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "query": request.url.query,
                "status_code": response.status_code,
                "client_ip": client_host,
                "duration_ms": duration_ms,
            },
        )
        response.headers["X-Request-ID"] = request_id
        return response
