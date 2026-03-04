from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models.activity import Activity
from app.models.activity_quality_label import ActivityQualityLabel
from app.models.activity_quality_metric import ActivityQualityMetric

WEAK_LABEL_SOURCE = "weak_rule"
WEAK_LABEL_VERSION_V1 = 1
DEFAULT_CREATED_BY = "ml-bootstrap-v1"

SPIKES_PER_KM_BAD_THRESHOLD = 6.0
JITTER_BAD_THRESHOLD = 0.35
MAX_SPEED_BAD_THRESHOLD_MPS = 12.0
DISTANCE_RATIO_LOW_THRESHOLD = 0.80
DISTANCE_RATIO_HIGH_THRESHOLD = 1.20

BAD_REASON_SPIKES = "high_spike_density"
BAD_REASON_JITTER = "extreme_jitter"
BAD_REASON_MAX_SPEED = "unrealistic_max_speed"
BAD_REASON_DISTANCE_MISMATCH = "severe_distance_mismatch"
GOOD_REASON_BASELINE = "within_expected_ranges"

ROOT_DIR = Path(__file__).resolve().parents[3]
DEFAULT_SUMMARY_PATH = ROOT_DIR / "artifacts/ml/bootstrap_summary.json"


@dataclass(frozen=True)
class WeakLabelDecision:
    label_bad: bool
    reasons: tuple[str, ...]
    confidence: float


def _clamp_confidence(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 3)


def _reason_csv(reasons: tuple[str, ...]) -> str:
    return ",".join(reasons)


def _parse_reason_csv(reason_csv: str | None) -> list[str]:
    if not reason_csv:
        return []
    return [token.strip() for token in reason_csv.split(",") if token.strip()]


def evaluate_weak_label(
    metric: ActivityQualityMetric, *, official_distance_m: float | None
) -> WeakLabelDecision:
    distance_km = metric.distance_m_gps / 1000.0 if metric.distance_m_gps > 0 else 0.0
    spikes_per_km = (metric.spike_count / distance_km) if distance_km > 0 else float(metric.spike_count)

    bad_reasons: list[str] = []

    if spikes_per_km >= SPIKES_PER_KM_BAD_THRESHOLD:
        bad_reasons.append(BAD_REASON_SPIKES)
    if metric.jitter_score >= JITTER_BAD_THRESHOLD:
        bad_reasons.append(BAD_REASON_JITTER)
    if metric.max_speed_mps >= MAX_SPEED_BAD_THRESHOLD_MPS:
        bad_reasons.append(BAD_REASON_MAX_SPEED)

    if official_distance_m is not None and official_distance_m > 0:
        distance_ratio = metric.distance_m_gps / official_distance_m
        if (
            distance_ratio <= DISTANCE_RATIO_LOW_THRESHOLD
            or distance_ratio >= DISTANCE_RATIO_HIGH_THRESHOLD
        ):
            bad_reasons.append(BAD_REASON_DISTANCE_MISMATCH)

    if bad_reasons:
        confidence = _clamp_confidence(0.65 + 0.10 * (len(bad_reasons) - 1))
        return WeakLabelDecision(
            label_bad=True,
            reasons=tuple(bad_reasons),
            confidence=confidence,
        )

    return WeakLabelDecision(
        label_bad=False,
        reasons=(GOOD_REASON_BASELINE,),
        confidence=0.55,
    )


def _upsert_weak_label(
    db: Session,
    *,
    activity_id: int,
    decision: WeakLabelDecision,
    created_by: str,
) -> str:
    label = (
        db.query(ActivityQualityLabel)
        .filter(ActivityQualityLabel.activity_id == activity_id)
        .one_or_none()
    )

    if label is not None and label.label_source == "manual":
        return "skipped_manual"
    if label is not None and label.label_source != WEAK_LABEL_SOURCE:
        return "skipped_existing_other_source"

    action = "updated"
    if label is None:
        label = ActivityQualityLabel(activity_id=activity_id)
        db.add(label)
        action = "created"

    label.label_bad = decision.label_bad
    label.label_source = WEAK_LABEL_SOURCE
    label.label_reason = _reason_csv(decision.reasons)
    label.label_confidence = decision.confidence
    label.label_version = WEAK_LABEL_VERSION_V1
    label.created_by = created_by
    return action


def _collect_distribution(db: Session) -> tuple[dict, list[dict]]:
    rows = (
        db.query(ActivityQualityLabel)
        .filter(ActivityQualityLabel.label_source == WEAK_LABEL_SOURCE)
        .all()
    )
    total = len(rows)
    bad = sum(1 for row in rows if row.label_bad)
    good = total - bad

    reason_counter: Counter[str] = Counter()
    for row in rows:
        for reason in _parse_reason_csv(row.label_reason):
            reason_counter[reason] += 1

    top_reasons = [
        {"reason": reason, "count": count}
        for reason, count in reason_counter.most_common(10)
    ]
    class_balance = {
        "total": total,
        "bad": bad,
        "good": good,
        "bad_ratio": round(bad / total, 4) if total else None,
    }
    return class_balance, top_reasons


def write_bootstrap_summary(summary: dict, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def bootstrap_weak_labels(
    db: Session,
    *,
    limit: int | None = None,
    offset: int = 0,
    created_by: str = DEFAULT_CREATED_BY,
    output_path: str | Path | None = DEFAULT_SUMMARY_PATH,
) -> dict:
    activity_ids_q = db.query(Activity.id).order_by(Activity.id.asc()).offset(offset)
    if limit is not None:
        activity_ids_q = activity_ids_q.limit(limit)
    activity_ids = [row[0] for row in activity_ids_q.all()]

    summary = {
        "ok": True,
        "source": WEAK_LABEL_SOURCE,
        "label_version": WEAK_LABEL_VERSION_V1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "selected_activities": len(activity_ids),
        "processed_with_metrics": 0,
        "created": 0,
        "updated": 0,
        "skipped_manual": 0,
        "skipped_existing_other_source": 0,
        "skipped_missing_metric": 0,
        "thresholds": {
            "spikes_per_km_bad": SPIKES_PER_KM_BAD_THRESHOLD,
            "jitter_bad": JITTER_BAD_THRESHOLD,
            "max_speed_bad_mps": MAX_SPEED_BAD_THRESHOLD_MPS,
            "distance_ratio_low": DISTANCE_RATIO_LOW_THRESHOLD,
            "distance_ratio_high": DISTANCE_RATIO_HIGH_THRESHOLD,
        },
    }

    for activity_id in activity_ids:
        activity = db.query(Activity).filter(Activity.id == activity_id).one()
        metric = (
            db.query(ActivityQualityMetric)
            .filter(ActivityQualityMetric.activity_id == activity_id)
            .one_or_none()
        )
        if metric is None:
            summary["skipped_missing_metric"] += 1
            continue

        decision = evaluate_weak_label(metric, official_distance_m=activity.distance_m)
        action = _upsert_weak_label(
            db,
            activity_id=activity_id,
            decision=decision,
            created_by=created_by,
        )
        summary["processed_with_metrics"] += 1
        summary[action] += 1

    db.commit()
    class_balance, top_reasons = _collect_distribution(db)
    summary["class_balance"] = class_balance
    summary["top_reasons"] = top_reasons

    if output_path is not None:
        path = write_bootstrap_summary(summary, output_path=output_path)
        summary["summary_path"] = str(path)

    return summary


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bootstrap weak labels from persisted quality metrics.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Optional max activities to scan.")
    parser.add_argument("--offset", type=int, default=0, help="Offset in ordered activities list.")
    parser.add_argument(
        "--created-by",
        default=DEFAULT_CREATED_BY,
        help="Metadata marker for label rows.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_SUMMARY_PATH),
        help="Path for JSON summary artifact.",
    )
    return parser


def main() -> int:
    parser = _build_arg_parser()
    args = parser.parse_args()

    with SessionLocal() as db:
        summary = bootstrap_weak_labels(
            db,
            limit=args.limit,
            offset=args.offset,
            created_by=args.created_by,
            output_path=args.output,
        )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

