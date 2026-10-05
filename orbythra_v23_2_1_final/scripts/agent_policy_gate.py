from __future__ import annotations

import json
import sys
from pathlib import Path

from app.agent_models import AgentActionRequest, AgentProfile, ToolProfile
from app.agent_policy import evaluate_agent_policy

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "benchmarks" / "agentic_policy_challenge_v1.json"


def run(path: Path) -> dict[str, object]:
    dataset = json.loads(path.read_text(encoding="utf-8"))
    results: list[dict[str, object]] = []
    passed = 0
    for scenario in dataset["scenarios"]:
        agent = AgentProfile(**scenario["agent"])
        tool = ToolProfile(**scenario["tool"])
        action = AgentActionRequest(**scenario["action"])
        context = scenario.get("context") or {}
        result = evaluate_agent_policy(
            agent,
            tool,
            action,
            run=context.get("run"),
            run_lookup_failed=bool(context.get("run_lookup_failed", False)),
            agent_action_count=int(context.get("agent_action_count", 0)),
            external_endpoint_allowed=bool(context.get("external_endpoint_allowed", True)),
        )
        expected = scenario["expected_decision"]
        required_reasons = set(scenario.get("required_reasons") or [])
        actual_reasons = set(result.reasons)
        exact = result.decision == expected and required_reasons.issubset(actual_reasons)
        if exact:
            passed += 1
        results.append({
            "id": scenario["id"],
            "expected_decision": expected,
            "actual_decision": result.decision,
            "required_reasons": sorted(required_reasons),
            "actual_reasons": list(result.reasons),
            "passed": exact,
        })
    count = len(results)
    rate = passed / count if count else 0.0
    minimum = float(dataset.get("minimum_exact_match_rate", 1.0))
    report = {
        "benchmark_id": dataset["benchmark_id"],
        "scenario_count": count,
        "passed_scenarios": passed,
        "exact_match_rate": rate,
        "minimum_exact_match_rate": minimum,
        "passed": rate >= minimum,
        "results": results,
        "validation_boundary": "Internal deterministic agent-policy regression corpus; not independent MCP/tool security validation or production safety evidence.",
    }
    return report


if __name__ == "__main__":
    dataset_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_DATASET
    report = run(dataset_path)
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["passed"] else 1)
