from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    DATABASE_URL: str = "postgresql+psycopg://app:app@localhost:5432/livemap"

    # Strava OAuth (application credentials)
    STRAVA_CLIENT_ID: str
    STRAVA_CLIENT_SECRET: str
    STRAVA_REDIRECT_URI: str
    STRAVA_SCOPES: str = "read,activity:read_all"
    AUTH_SUCCESS_REDIRECT_URL: str = "/"

    # Observability
    LOG_LEVEL: str = "INFO"
    SENTRY_DSN: str | None = None
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0


settings = Settings()
