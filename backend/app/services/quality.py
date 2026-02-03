from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class QualityReport:
    point_count: int
    duration_s: int
    distance_m: float
    max_speed_mps: float
    spike_count: int
    stopped_time_s: int
    stop_segments: int
    jitter_score: float


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Approximate distance in meters using the haversine formula."""
    from math import radians, sin, cos, asin, sqrt

    R = 6371000.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * R * asin(sqrt(a))


def compute_quality(
    latlons: List[Tuple[float, float]],
    times: List[int],
    spike_speed_mps: float = 12.0,   # ~43 km/h; default spike threshold for running
    stop_speed_mps: float = 0.6,     # below this is treated as stopped
    stop_min_duration_s: int = 10,   # minimum duration to count a stop
) -> QualityReport:
    n = len(latlons)
    if n < 2:
        return QualityReport(
            point_count=n,
            duration_s=0,
            distance_m=0.0,
            max_speed_mps=0.0,
            spike_count=0,
            stopped_time_s=0,
            stop_segments=0,
            jitter_score=0.0,
        )

    dist_total = 0.0
    max_speed = 0.0
    spike_count = 0

    # Stop detection state.
    stopped_time = 0
    stop_segments = 0
    in_stop = False
    current_stop_time = 0

    # Collect speeds for jitter metric.
    speeds = []

    for i in range(1, n):
        (lat1, lon1) = latlons[i - 1]
        (lat2, lon2) = latlons[i]
        dt = times[i] - times[i - 1]
        if dt <= 0:
            continue

        d = haversine_m(lat1, lon1, lat2, lon2)
        v = d / dt

        dist_total += d
        speeds.append(v)
        if v > max_speed:
            max_speed = v

        if v >= spike_speed_mps:
            spike_count += 1

        # Stop state machine.
        if v <= stop_speed_mps:
            current_stop_time += dt
            if not in_stop:
                in_stop = True
        else:
            if in_stop:
                if current_stop_time >= stop_min_duration_s:
                    stopped_time += current_stop_time
                    stop_segments += 1
                current_stop_time = 0
                in_stop = False

    # Finalize trailing stop segment.
    if in_stop and current_stop_time >= stop_min_duration_s:
        stopped_time += current_stop_time
        stop_segments += 1

    duration = max(times) - min(times) if times else 0

    # Jitter score: mean absolute delta of consecutive speeds.
    jitter = 0.0
    if len(speeds) >= 2:
        diffs = [abs(speeds[i] - speeds[i - 1]) for i in range(1, len(speeds))]
        jitter = sum(diffs) / len(diffs)

    return QualityReport(
        point_count=n,
        duration_s=duration,
        distance_m=dist_total,
        max_speed_mps=max_speed,
        spike_count=spike_count,
        stopped_time_s=stopped_time,
        stop_segments=stop_segments,
        jitter_score=jitter,
    )
