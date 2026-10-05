from __future__ import annotations

from typing import Any

RISK = {"low": 0, "moderate": 1, "high": 2, "critical": 3}


def learning_gate(*, baseline_score: float, candidate_score: float, minimum_improvement: float) -> tuple[str, float]:
    improvement = round(float(candidate_score) - float(baseline_score), 10)
    return ("ACCEPT" if improvement >= float(minimum_improvement) else "REJECT", improvement)


def select_strategy(strategies: list[dict[str, Any]], *, domain: str, required_capabilities: list[str], max_risk_tier: str) -> tuple[dict[str, Any] | None, float | None]:
    required = set(required_capabilities)
    candidates: list[tuple[float, dict[str, Any]]] = []
    for strategy in strategies:
        if not strategy.get("enabled", True):
            continue
        domains = set(strategy.get("domains", []))
        if domains and domain not in domains:
            continue
        if not required.issubset(set(strategy.get("capabilities", []))):
            continue
        if RISK.get(str(strategy.get("risk_tier", "critical")), 3) > RISK[max_risk_tier]:
            continue
        utility = 0.70 * float(strategy["success_score"]) + 0.15 * (1.0 - float(strategy["latency_score"])) + 0.15 * (1.0 - float(strategy["cost_score"]))
        candidates.append((round(utility, 8), strategy))
    if not candidates:
        return None, None
    utility, selected = sorted(candidates, key=lambda item: (-item[0], str(item[1]["strategy_id"])))[0]
    return selected, utility
