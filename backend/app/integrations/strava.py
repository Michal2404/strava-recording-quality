import httpx


class StravaClient:
    def __init__(self, access_token: str):
        self.access_token = access_token

    def _headers(self):
        return {"Authorization": f"Bearer {self.access_token}"}

    def list_activities(self, per_page: int = 30, page: int = 1):
        url = "https://www.strava.com/api/v3/athlete/activities"
        params = {"per_page": per_page, "page": page}
        r = httpx.get(url, headers=self._headers(), params=params, timeout=20.0)
        r.raise_for_status()
        return r.json()

    def get_activity_streams(self, activity_id: int, keys: str = "latlng,time,altitude"):
        url = f"https://www.strava.com/api/v3/activities/{activity_id}/streams"
        params = {
            "keys": keys,
            "key_by_type": "true",
        }
        r = httpx.get(url, headers=self._headers(), params=params, timeout=20.0)
        r.raise_for_status()
        return r.json()
