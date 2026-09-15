from __future__ import annotations

import argparse
import json
import statistics
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    return float(value)


def evaluate(payload: dict[str, Any]) -> dict[str, Any]:
    evaluator = payload.get("evaluator") or {}
    cases = payload.get("cases") or []
    if not isinstance(evaluator, dict) or not isinstance(cases, list) or not cases:
        raise ValueError("payload requires evaluator metadata and a non-empty cases list")

    systems: dict[str, list[float]] = {}
    per_case: list[dict[str, Any]] = []
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"case {index} must be an object")
        scores = case.get("scores") or {}
        if not isinstance(scores, dict) or len(scores) < 2:
            raise ValueError(f"case {index} requires scores for at least two systems")
        normalized = {name: _number(score, f"case {index} score {name}") for name, score in scores.items()}
        for name, score in normalized.items():
            systems.setdefault(str(name), []).append(score)
        top_score = max(normalized.values())
        winners = sorted(name for name, score in normalized.items() if score == top_score)
        per_case.append(
            {
                "case_id": str(case.get("case_id") or index),
                "scores": normalized,
                "winners": winners,
                "notes": case.get("notes"),
            }
        )

    expected_count = len(cases)
    incomplete = [name for name, values in systems.items() if len(values) != expected_count]
    if incomplete:
        raise ValueError("every system must be scored on every case: " + ", ".join(sorted(incomplete)))

    summary: dict[str, Any] = {}
    wins: CounterLike = {}
    for row in per_case:
        share = 1.0 / len(row["winners"])
        for winner in row["winners"]:
            wins[winner] = wins.get(winner, 0.0) + share
    for name, values in sorted(systems.items()):
        summary[name] = {
            "mean_score": round(statistics.fmean(values), 6),
            "median_score": round(statistics.median(values), 6),
            "min_score": round(min(values), 6),
            "max_score": round(max(values), 6),
            "win_share": round(wins.get(name, 0.0) / expected_count, 6),
            "case_count": expected_count,
        }

    independent = bool(evaluator.get("independent_external_validation"))
    third_party = bool(evaluator.get("third_party_baseline_comparison"))
    assessor = str(evaluator.get("assessor") or "").strip()
    evidence_uri = str(evaluator.get("evidence_uri") or "").strip()
    external_claim_ready = independent and third_party and bool(assessor) and bool(evidence_uri)

    return {
        "schema": "orbythra.external-benchmark.v1",
        "product": "ORBYTHRA",
        "generated_at": _utc_now(),
        "evaluator": evaluator,
        "case_count": expected_count,
        "systems": summary,
        "cases": per_case,
        "external_claim_ready": external_claim_ready,
        "claim_boundary": (
            "This aggregator does not make a benchmark independent. External validation is claim-ready "
            "only when a named independent assessor supplies the cases/results, compares at least one "
            "third-party baseline, and provides an evidence location that can be reviewed."
        ),
    }


CounterLike = dict[str, float]


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate externally evaluated ORBYTHRA benchmark results")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = evaluate(payload)
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
