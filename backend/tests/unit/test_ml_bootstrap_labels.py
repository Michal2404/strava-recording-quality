from __future__ import annotations

from types import SimpleNamespace

from app.ml.bootstrap_labels import (
    BAD_REASON_DISTANCE_MISMATCH,
    BAD_REASON_JITTER,
    BAD_REASON_MAX_SPEED,
    BAD_REASON_SPIKES,
    GOOD_REASON_BASELINE,
    evaluate_weak_label,
)


def _metric(**overrides):
    data = {
        "distance_m_gps": 10_000.0,
        "spike_count": 4,
        "jitter_score": 0.12,
        "max_speed_mps": 5.5,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_evaluate_weak_label_good_baseline():
    decision = evaluate_weak_label(_metric(), official_distance_m=10_000.0)

    assert decision.label_bad is False
    assert decision.reasons == (GOOD_REASON_BASELINE,)
    assert decision.confidence == 0.55


def test_evaluate_weak_label_high_spike_density_is_bad():
    decision = evaluate_weak_label(
        _metric(spike_count=120, distance_m_gps=10_000.0),
        official_distance_m=10_000.0,
    )

    assert decision.label_bad is True
    assert BAD_REASON_SPIKES in decision.reasons
    assert decision.confidence >= 0.65


def test_evaluate_weak_label_multiple_bad_rules_raise_confidence():
    decision = evaluate_weak_label(
        _metric(
            spike_count=150,
            jitter_score=0.6,
            max_speed_mps=16.0,
            distance_m_gps=12_000.0,
        ),
        official_distance_m=8_000.0,
    )

    assert decision.label_bad is True
    assert BAD_REASON_SPIKES in decision.reasons
    assert BAD_REASON_JITTER in decision.reasons
    assert BAD_REASON_MAX_SPEED in decision.reasons
    assert BAD_REASON_DISTANCE_MISMATCH in decision.reasons
    assert decision.confidence == 0.95


def test_distance_mismatch_rule_requires_official_distance():
    decision = evaluate_weak_label(
        _metric(distance_m_gps=20_000.0),
        official_distance_m=None,
    )

    assert decision.label_bad is False
    assert BAD_REASON_DISTANCE_MISMATCH not in decision.reasons

