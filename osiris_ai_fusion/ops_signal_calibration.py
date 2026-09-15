from __future__ import annotations

import argparse
import json
import math
import statistics
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _float01(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{label} must be between 0 and 1")
    return number


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    mean_x = statistics.fmean(xs)
    mean_y = statistics.fmean(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    denom_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    denom_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if denom_x == 0 or denom_y == 0:
        return None
    return round(numerator / (denom_x * denom_y), 6)


def calibrate(payload: dict[str, Any], bins: int = 10) -> dict[str, Any]:
    if bins < 2 or bins > 50:
        raise ValueError("bins must be between 2 and 50")
    evaluator = payload.get("evaluator") or {}
    records = payload.get("records") or []
    if not isinstance(evaluator, dict) or not isinstance(records, list) or not records:
        raise ValueError("payload requires evaluator metadata and records")

    scores: list[float] = []
    outcomes: list[float] = []
    normalized: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"record {index} must be an object")
        score = _float01(record.get("signal_score"), f"record {index} signal_score")
        outcome = _float01(record.get("outcome"), f"record {index} outcome")
        scores.append(score)
        outcomes.append(outcome)
        normalized.append(
            {
                "record_id": str(record.get("record_id") or index),
                "signal_score": score,
                "outcome": outcome,
                "timestamp": record.get("timestamp"),
            }
        )

    brier = statistics.fmean((score - outcome) ** 2 for score, outcome in zip(scores, outcomes, strict=True))
    bucket_rows: list[dict[str, Any]] = []
    weighted_gap = 0.0
    for bucket in range(bins):
        lower = bucket / bins
        upper = (bucket + 1) / bins
        indexes = [
            index
            for index, score in enumerate(scores)
            if lower <= score < upper or (bucket == bins - 1 and score == 1.0)
        ]
        if not indexes:
            continue
        predicted = statistics.fmean(scores[index] for index in indexes)
        observed = statistics.fmean(outcomes[index] for index in indexes)
        gap = abs(predicted - observed)
        weighted_gap += gap * len(indexes) / len(records)
        bucket_rows.append(
            {
                "lower": round(lower, 6),
                "upper": round(upper, 6),
                "count": len(indexes),
                "mean_prediction": round(predicted, 6),
                "observed_rate": round(observed, 6),
                "absolute_gap": round(gap, 6),
            }
        )

    independent = bool(evaluator.get("independent_external_validation"))
    assessor = str(evaluator.get("assessor") or "").strip()
    evidence_uri = str(evaluator.get("evidence_uri") or "").strip()
    external_claim_ready = independent and bool(assessor) and bool(evidence_uri)
    return {
        "schema": "orbythra.signal-calibration.v1",
        "product": "ORBYTHRA",
        "generated_at": _utc_now(),
        "record_count": len(records),
        "evaluator": evaluator,
        "metrics": {
            "brier_score": round(brier, 6),
            "expected_calibration_error": round(weighted_gap, 6),
            "pearson_signal_outcome": _pearson(scores, outcomes),
            "mean_signal": round(statistics.fmean(scores), 6),
            "mean_outcome": round(statistics.fmean(outcomes), 6),
        },
        "calibration_bins": bucket_rows,
        "records": normalized,
        "external_claim_ready": external_claim_ready,
        "claim_boundary": (
            "Calibration metrics only describe the supplied outcome dataset. ORBYTHRA proprietary "
            "signals are externally calibrated only when a named independent assessor supplies or "
            "audits the outcomes and a reviewable evidence location is retained."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate ORBYTHRA proprietary signals on observed outcomes")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output")
    parser.add_argument("--bins", type=int, default=10)
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = calibrate(payload, bins=args.bins)
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
