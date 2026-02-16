from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)


class StravaClient:
    BASE_URL = "https://www.strava.com/api/v3"
    TOKEN_URL = "https://www.strava.com/oauth/token"
    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(
        self,
        access_token: str,
        refresh_token: str | None = None,
        expires_at: int | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        timeout_s: float = 20.0,
        max_retries: int = 3,
        backoff_base_s: float = 0.5,
        refresh_leeway_s: int = 60,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_at = expires_at
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.backoff_base_s = backoff_base_s
        self.refresh_leeway_s = refresh_leeway_s
        self._token_was_refreshed = False

    def _headers(self):
        return {"Authorization": f"Bearer {self.access_token}"}

    @property
    def token_was_refreshed(self) -> bool:
        return self._token_was_refreshed

    def _can_refresh(self) -> bool:
        return bool(self.refresh_token and self.client_id and self.client_secret)

    def _token_is_expired_or_near_expiry(self) -> bool:
        if self.expires_at is None:
            return False
        now = int(datetime.now(timezone.utc).timestamp())
        return now >= (self.expires_at - self.refresh_leeway_s)

    def _ensure_valid_token(self) -> None:
        if self._token_is_expired_or_near_expiry() and self._can_refresh():
            logger.info("Strava token near expiry; refreshing before API request")
            self.refresh_access_token()

    def refresh_access_token(self) -> dict:
        if not self._can_refresh():
            raise RuntimeError("Cannot refresh Strava token without refresh credentials")

        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
        }
        r = httpx.post(self.TOKEN_URL, data=payload, timeout=self.timeout_s)
        r.raise_for_status()
        data = r.json()

        self.access_token = data["access_token"]
        self.refresh_token = data.get("refresh_token", self.refresh_token)
        self.expires_at = data.get("expires_at", self.expires_at)
        self._token_was_refreshed = True
        return data

    @staticmethod
    def _retry_after_seconds(response: httpx.Response) -> float | None:
        value = response.headers.get("Retry-After")
        if value is None:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    def _sleep_before_retry(self, attempt: int, reason: str, retry_after_s: float | None = None) -> None:
        delay = retry_after_s if retry_after_s is not None else self.backoff_base_s * (2**attempt)
        delay = min(delay, 30.0)
        logger.warning("Retrying Strava request after %s (attempt=%s delay=%.2fs)", reason, attempt + 1, delay)
        time.sleep(delay)

    def _request_json(self, method: str, path: str, *, params: dict | None = None) -> dict | list:
        self._ensure_valid_token()
        url = f"{self.BASE_URL}/{path.lstrip('/')}"
        refreshed_after_401 = False

        for attempt in range(self.max_retries + 1):
            try:
                r = httpx.request(
                    method=method,
                    url=url,
                    headers=self._headers(),
                    params=params,
                    timeout=self.timeout_s,
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt >= self.max_retries:
                    raise
                self._sleep_before_retry(attempt, reason=exc.__class__.__name__)
                continue

            if r.status_code == 401 and not refreshed_after_401 and self._can_refresh():
                logger.warning("Strava returned 401 for %s; refreshing token and retrying", path)
                self.refresh_access_token()
                refreshed_after_401 = True
                continue

            if r.status_code in self.RETRYABLE_STATUS_CODES and attempt < self.max_retries:
                self._sleep_before_retry(
                    attempt,
                    reason=f"HTTP {r.status_code}",
                    retry_after_s=self._retry_after_seconds(r),
                )
                continue

            r.raise_for_status()
            return r.json()

        raise RuntimeError("Strava request retry loop ended unexpectedly")

    def list_activities(self, per_page: int = 30, page: int = 1):
        params = {"per_page": per_page, "page": page}
        return self._request_json("GET", "/athlete/activities", params=params)

    def get_activity_streams(self, activity_id: int, keys: str = "latlng,time,altitude"):
        params = {
            "keys": keys,
            "key_by_type": "true",
        }
        return self._request_json("GET", f"/activities/{activity_id}/streams", params=params)
