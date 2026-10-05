from __future__ import annotations

import json
from pathlib import Path

from app.adaptive_core import learning_gate, select_strategy

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "benchmarks" / "adaptive_generalist_challenge_v1.json"


def main() -> None:
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    results = []
    exact = 0
    for scenario in dataset["scenarios"]:
        inp = scenario["input"]
        if scenario["kind"] == "learning":
            decision, improvement = learning_gate(**inp)
            actual = {"decision": decision, "improvement": improvement}
        elif scenario["kind"] == "route":
            selected, utility = select_strategy(inp["strategies"], domain=inp["domain"], required_capabilities=inp["required_capabilities"], max_risk_tier=inp["max_risk_tier"])
            actual = {"strategy_id": None if selected is None else selected["strategy_id"], "utility_score": utility}
        else:
            raise SystemExit(f"unknown scenario kind: {scenario['kind']}")
        passed = actual == scenario["expected"]
        exact += int(passed)
        results.append({"id": scenario["id"], "passed": passed, "actual": actual, "expected": scenario["expected"]})
    total = len(results)
    rate = 0.0 if total == 0 else exact / total
    output = {"name": dataset["name"], "total": total, "exact": exact, "exact_match_rate": rate, "minimum_exact_match_rate": dataset["minimum_exact_match_rate"], "results": results, "boundary": dataset["boundary"]}
    print(json.dumps(output, indent=2, sort_keys=True))
    if rate < float(dataset["minimum_exact_match_rate"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
