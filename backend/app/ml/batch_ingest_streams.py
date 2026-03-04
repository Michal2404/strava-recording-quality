from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models.activity import Activity
from app.models.activity_quality_metric import ActivityQualityMetric
from app.services.stream_ingest import (
    ActivityNotFoundError,
    MissingStreamDataError,
    MissingTokenError,
    ingest_streams_for_activity,
)

ROOT_DIR = Path(__file__).resolve().parents[3]
DEFAULT_SUMMARY_PATH = ROOT_DIR / "artifacts/ml/ingest_summary.json"


def _parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return parsed


def _write_summary(summary: dict, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _query_target_activity_ids(
    db: Session,
    *,
    only_missing_metrics: bool,
    sport_type: str | None,
    after: datetime | None,
    before: datetime | None,
    limit: int | None,
    offset: int,
) -> list[int]:
    q = db.query(Activity.id)

    if only_missing_metrics:
        q = q.outerjoin(ActivityQualityMetric, ActivityQualityMetric.activity_id == Activity.id).filter(
            ActivityQualityMetric.id.is_(None)
        )
    if sport_type:
        q = q.filter(Activity.sport_type == sport_type)
    if after:
        q = q.filter(Activity.start_date.is_not(None)).filter(Activity.start_date >= after)
    if before:
        q = q.filter(Activity.start_date.is_not(None)).filter(Activity.start_date <= before)

    q = q.order_by(Activity.start_date.desc().nullslast(), Activity.id.desc()).offset(offset)
    if limit is not None:
        q = q.limit(limit)
    return [row[0] for row in q.all()]


def backfill_activity_streams(
    db: Session,
    *,
    only_missing_metrics: bool = True,
    sport_type: str | None = None,
    after: datetime | None = None,
    before: datetime | None = None,
    limit: int | None = None,
    offset: int = 0,
    output_path: str | Path | None = DEFAULT_SUMMARY_PATH,
) -> dict:
    activity_ids = _query_target_activity_ids(
        db,
        only_missing_metrics=only_missing_metrics,
        sport_type=sport_type,
        after=after,
        before=before,
        limit=limit,
        offset=offset,
    )

    summary = {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "selected_activities": len(activity_ids),
        "only_missing_metrics": only_missing_metrics,
        "sport_type": sport_type,
        "after": after.isoformat() if after else None,
        "before": before.isoformat() if before else None,
        "ingested": 0,
        "missing_stream_data": 0,
        "missing_token": 0,
        "not_found": 0,
        "failed": 0,
        "total_points_written": 0,
        "error_examples": [],
    }

    for activity_id in activity_ids:
        try:
            result = ingest_streams_for_activity(
                db,
                activity_id=activity_id,
                commit=True,
            )
            summary["ingested"] += 1
            summary["total_points_written"] += result.points
        except MissingStreamDataError as exc:
            db.rollback()
            summary["missing_stream_data"] += 1
            summary["error_examples"].append({"activity_id": activity_id, "error": str(exc)})
        except MissingTokenError as exc:
            db.rollback()
            summary["missing_token"] += 1
            summary["error_examples"].append({"activity_id": activity_id, "error": str(exc)})
        except ActivityNotFoundError as exc:
            db.rollback()
            summary["not_found"] += 1
            summary["error_examples"].append({"activity_id": activity_id, "error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            summary["failed"] += 1
            summary["error_examples"].append({"activity_id": activity_id, "error": f"{type(exc).__name__}: {exc}"})

    # Keep artifact compact while still useful for debugging.
    if len(summary["error_examples"]) > 20:
        summary["error_examples"] = summary["error_examples"][:20]
        summary["error_examples_truncated"] = True
    else:
        summary["error_examples_truncated"] = False

    if output_path is not None:
        path = _write_summary(summary, output_path=output_path)
        summary["summary_path"] = str(path)
    return summary


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Batch-ingest Strava streams for many synced activities.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Max number of activities to process.")
    parser.add_argument("--offset", type=int, default=0, help="Offset into the selected activity set.")
    parser.add_argument(
        "--only-missing-metrics",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="When true, ingest only activities without activity_quality_metrics rows.",
    )
    parser.add_argument("--sport-type", default=None, help="Optional exact sport_type filter (e.g. Run).")
    parser.add_argument(
        "--after",
        default=None,
        help="ISO datetime lower bound for activity.start_date, e.g. 2023-01-01T00:00:00Z.",
    )
    parser.add_argument(
        "--before",
        default=None,
        help="ISO datetime upper bound for activity.start_date, e.g. 2023-05-31T23:59:59Z.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_SUMMARY_PATH),
        help="Path for ingest summary JSON artifact.",
    )
    return parser


def main() -> int:
    parser = _build_arg_parser()
    args = parser.parse_args()
    after = _parse_dt(args.after)
    before = _parse_dt(args.before)

    with SessionLocal() as db:
        summary = backfill_activity_streams(
            db,
            only_missing_metrics=args.only_missing_metrics,
            sport_type=args.sport_type,
            after=after,
            before=before,
            limit=args.limit,
            offset=args.offset,
            output_path=args.output,
        )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

