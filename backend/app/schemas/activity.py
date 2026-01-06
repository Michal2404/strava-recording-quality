from datetime import datetime
from pydantic import BaseModel


class ActivityOut(BaseModel):
    id: int
    strava_activity_id: int
    name: str | None
    sport_type: str | None
    start_date: datetime | None
    distance_m: float | None
    moving_time_s: int | None
    elevation_gain_m: float | None

    class Config:
        from_attributes = True
