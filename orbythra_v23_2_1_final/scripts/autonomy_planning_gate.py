from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.autonomy import _select_skills

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "benchmarks" / "autonomy_planning_challenge_v1.json"


def main() -> None:
    raw = DATASET.read_bytes()
    dataset = json.loads(raw)
    results = []
    matched = 0
    for scenario in dataset["scenarios"]:
        selected, missing = _select_skills(scenario["required_capabilities"], scenario["viable_skills"])
        actual_selected = [item["skill_id"] for item in selected]
        ok = actual_selected == scenario["expected_selected"] and missing == scenario["expected_missing"]
        matched += int(ok)
        results.append({
            "id": scenario["id"],
            "pass": ok,
            "selected": actual_selected,
            "missing": missing,
        })
    total = len(results)
    rate = 0.0 if total == 0 else matched / total
    report = {
        "dataset": DATASET.name,
        "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "exact_matches": matched,
        "total": total,
        "exact_match_rate": rate,
        "required_rate": float(dataset["minimum_exact_match_rate"]),
        "claim_boundary": dataset["claim_boundary"],
        "results": results,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    if rate < float(dataset["minimum_exact_match_rate"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
