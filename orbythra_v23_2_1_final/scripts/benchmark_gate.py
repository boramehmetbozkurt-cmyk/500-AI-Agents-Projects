from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

from app.models import VerifyRequest
from app.services.evidence import verify

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "benchmarks" / "assurance_challenge_v2.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(dataset_path: Path = DEFAULT_DATASET) -> dict[str, object]:
    raw = json.loads(dataset_path.read_text(encoding="utf-8"))
    fixed_now = datetime.fromisoformat(raw["fixed_now"])
    outcomes: list[dict[str, object]] = []
    exact = 0

    for scenario in raw["scenarios"]:
        request = VerifyRequest(
            claims=scenario["claims"],
            evidence=scenario.get("evidence", []),
            minimum_support=scenario.get("minimum_support", 0.75),
            minimum_authority=scenario.get("minimum_authority", 0.60),
            max_age_days=scenario.get("max_age_days", 30),
        )
        result = verify(request, now=fixed_now)
        actual_statuses = [item.status for item in result.verdicts]
        passed = (
            result.disposition == scenario["expected_disposition"]
            and actual_statuses == scenario["expected_statuses"]
        )
        exact += int(passed)
        outcomes.append({
            "scenario_id": scenario["id"],
            "passed": passed,
            "expected_disposition": scenario["expected_disposition"],
            "actual_disposition": result.disposition,
            "expected_statuses": scenario["expected_statuses"],
            "actual_statuses": actual_statuses,
        })

    count = len(outcomes)
    exact_match_rate = exact / max(1, count)
    threshold = float(raw.get("minimum_exact_match_rate", 1.0))
    report = {
        "benchmark_id": raw["benchmark_id"],
        "dataset_sha256": sha256_file(dataset_path),
        "scenario_count": count,
        "exact_matches": exact,
        "exact_match_rate": round(exact_match_rate, 6),
        "acceptance_threshold": threshold,
        "acceptance_passed": exact_match_rate >= threshold,
        "validation_boundary": "deterministic internal/reproducible benchmark; not independent validation or a measured real-world hallucination reduction rate",
        "outcomes": outcomes,
    }
    return report


def main() -> int:
    path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_DATASET
    report = run(path)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["acceptance_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
