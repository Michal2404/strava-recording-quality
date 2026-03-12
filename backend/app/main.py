from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import settings
from app.core.logging_setup import configure_logging
from app.core.observability import setup_observability
from app.routes.auth import router as auth_router
from app.routes.sync import router as sync_router
from app.routes.activities import router as activities_router
from app.routes.streams import router as streams_router
from app.routes.ml import router as ml_router

configure_logging(settings.LOG_LEVEL)

app = FastAPI(title="LiveMap Coach")
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SESSION_SECRET,
    session_cookie=settings.SESSION_COOKIE_NAME,
    max_age=settings.SESSION_MAX_AGE_SECONDS,
    same_site="lax",
    https_only=settings.SESSION_COOKIE_SECURE,
)
setup_observability(app, settings)

app.include_router(auth_router)
app.include_router(sync_router)
app.include_router(activities_router)
app.include_router(streams_router)
app.include_router(ml_router)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/health")
def health():
    return {"status": "ok"}
