from __future__ import annotations

from dataclasses import dataclass

from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy.orm import Session

from app.models.activity import Activity
from app.models.activity_point import ActivityPoint
from app.models.strava_token import StravaToken
from app.models.user import User
from app.services.quality_metrics import upsert_quality_metric_from_series
from app.services.strava_session import build_strava_client, persist_refreshed_token


class StreamIngestError(ValueError):
    """Base class for stream ingestion errors."""


class ActivityNotFoundError(StreamIngestError):
    """Activity row does not exist."""


class MissingTokenError(StreamIngestError):
    """No Strava token exists for activity owner."""


class MissingStreamDataError(StreamIngestError):
    """Strava stream payload is missing required keys."""


@dataclass(frozen=True)
class StreamIngestResult:
    activity_id: int
    points: int


def ingest_streams_for_activity(
    db: Session,
    *,
    activity_id: int,
    commit: bool = True,
) -> StreamIngestResult:
    activity = db.query(Activity).filter(Activity.id == activity_id).one_or_none()
    if not activity:
        raise ActivityNotFoundError("Activity not found")

    user = db.query(User).filter(User.id == activity.user_id).one_or_none()
    if not user:
        raise ActivityNotFoundError("Activity user not found")

    token = db.query(StravaToken).filter(StravaToken.user_id == user.id).one_or_none()
    if token is None:
        raise MissingTokenError("No Strava token found for activity user")

    client = build_strava_client(token)
    streams = client.get_activity_streams(activity.strava_activity_id)
    persist_refreshed_token(db, token, client, commit=False)

    latlng = streams.get("latlng", {}).get("data")
    times = streams.get("time", {}).get("data")
    altitude = streams.get("altitude", {}).get("data")

    if not latlng or not times:
        raise MissingStreamDataError("Missing latlng or time streams")

    db.query(ActivityPoint).filter(ActivityPoint.activity_id == activity.id).delete()

    points = []
    quality_latlons: list[tuple[float, float]] = []
    quality_times: list[int] = []

    for i, (coord, t) in enumerate(zip(latlng, times)):
        lon, lat = coord[1], coord[0]
        point = ActivityPoint(
            activity_id=activity.id,
            seq=i,
            time_s=t,
            geom=from_shape(Point(lon, lat), srid=4326),
            ele_m=altitude[i] if altitude and i < len(altitude) else None,
        )
        points.append(point)
        quality_latlons.append((lat, lon))
        quality_times.append(int(t))

    db.bulk_save_objects(points)
    upsert_quality_metric_from_series(
        db,
        activity_id=activity.id,
        latlons=quality_latlons,
        times=quality_times,
    )

    if commit:
        db.commit()

    return StreamIngestResult(activity_id=activity.id, points=len(points))

