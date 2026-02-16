import pytest

from app.services.quality import compute_quality, haversine_m


def test_compute_quality_for_simple_two_point_track():
    latlons = [(50.0, 19.0), (50.0001, 19.0001)]
    times = [0, 10]

    report = compute_quality(latlons, times)

    expected_distance = haversine_m(50.0, 19.0, 50.0001, 19.0001)
    assert report.point_count == 2
    assert report.duration_s == 10
    assert report.distance_m == pytest.approx(expected_distance, rel=1e-6)
    assert report.max_speed_mps == pytest.approx(expected_distance / 10.0, rel=1e-6)
    assert report.spike_count == 0
    assert report.stopped_time_s == 0
    assert report.stop_segments == 0
    assert report.jitter_score == 0.0


def test_compute_quality_detects_spikes_and_stop_segments():
    latlons = [
        (0.0, 0.0),      # t=0
        (0.0, 0.0),      # stop for 15s
        (0.001, 0.0),    # fast jump over 5s -> spike
        (0.001, 0.0),    # stop for 15s
    ]
    times = [0, 15, 20, 35]

    report = compute_quality(latlons, times)

    assert report.point_count == 4
    assert report.duration_s == 35
    assert report.spike_count == 1
    assert report.stop_segments == 2
    assert report.stopped_time_s == 30
    assert report.jitter_score > 20.0


def test_compute_quality_skips_non_increasing_timestamps():
    latlons = [(0.0, 0.0), (0.0001, 0.0), (0.0002, 0.0)]
    times = [0, 0, 10]  # first segment ignored because dt = 0

    report = compute_quality(latlons, times)
    expected_distance = haversine_m(0.0001, 0.0, 0.0002, 0.0)

    assert report.point_count == 3
    assert report.duration_s == 10
    assert report.distance_m == pytest.approx(expected_distance, rel=1e-6)
