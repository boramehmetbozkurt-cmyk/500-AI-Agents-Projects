from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time
from pathlib import Path
from typing import Any

import httpx

DEFAULT_SUITE = Path(__file__).resolve().parent / "benchmarks" / "adaptive_cognition_v1.json"


def _requirement_checks(requirements: list[str], result: dict[str, Any]) -> dict[str, bool]:
    report = result.get("report") or {}
    evaluation = result.get("self_evaluation") or {}
    adaptation = result.get("adaptation") or {}
    memory = result.get("memory") or {}
    checks: dict[str, bool] = {}
    for requirement in requirements:
        if requirement in {"evidence", "fresh_evidence", "current_sources", "citation_discipline"}:
            checks[requirement] = bool(result.get("evidence_index"))
        elif requirement in {"timeline", "history"}:
            checks[requirement] = bool(report.get("historical_timeline"))
        elif requirement in {"map", "spatial_uncertainty"}:
            checks[requirement] = bool(report.get("map_markers")) or bool(report.get("spatial_summary"))
        elif requirement in {"ideas", "experiments", "proposal_fact_separation", "idea_discipline"}:
            ideas = report.get("developed_ideas") or []
            checks[requirement] = bool(ideas) and all(
                isinstance(item, dict) and item.get("title") and item.get("thesis")
                for item in ideas
            )
        elif requirement in {"self_evaluation", "calibration"}:
            checks[requirement] = isinstance(evaluation.get("score"), (int, float))
        elif requirement in {"memory", "workspace_memory_only", "no_cross_tenant_recall"}:
            checks[requirement] = bool(memory.get("workspace_isolated"))
        elif requirement in {"max_one_refinement", "no_new_tools_on_refinement", "bounded_autonomy"}:
            checks[requirement] = (
                int(adaptation.get("passes", 0)) <= 1
                and int(adaptation.get("external_tool_calls", 0)) == 0
            )
        elif requirement == "refuse_to_invent_coordinates":
            markers = report.get("map_markers") or []
            checks[requirement] = all(
                isinstance(item, dict)
                and isinstance(item.get("lat"), (int, float))
                and isinstance(item.get("lon"), (int, float))
                for item in markers
            )
        elif requirement in {"goal_decomposition", "comparison"}:
            plan = result.get("cognitive_plan") or {}
            checks[requirement] = len(plan.get("objectives") or []) >= 2
        elif requirement in {"uncertainty", "data_gaps"}:
            checks[requirement] = bool(report.get("data_gaps"))
        elif requirement == "memory_not_evidence":
            checks[requirement] = bool(result.get("evidence_index"))
        elif requirement == "freshness":
            checks[requirement] = bool(result.get("evidence_index"))
        elif requirement == "safe_ideation":
            checks[requirement] = bool(report.get("developed_ideas")) or bool(report.get("next_checks"))
        elif requirement == "no_active_intrusion":
            tools = set(result.get("planned_tools") or [])
            checks[requirement] = not tools.intersection(
                {"active_scanning", "exploitation", "credential_access"}
            )
        else:
            checks[requirement] = True
    return checks


async def _run_case(
    client: httpx.AsyncClient,
    base_url: str,
    case: dict[str, Any],
    headers: dict[str, str],
) -> dict[str, Any]:
    started = time.perf_counter()
    response = await client.post(
        base_url.rstrip("/") + "/investigate",
        headers=headers,
        json={
            "query": case["query"],
            "save": False,
            "scope": {"workspace_id": "adaptive-benchmark"},
        },
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    response.raise_for_status()
    result = response.json()
    checks = _requirement_checks(list(case.get("requires") or []), result)
    evaluation = result.get("self_evaluation") or {}
    quality_score = float(evaluation.get("score", 0.0))
    structural_score = sum(checks.values()) / max(1, len(checks))
    case_score = round(0.7 * quality_score + 0.3 * structural_score, 4)
    return {
        "id": case["id"],
        "language": case.get("language"),
        "latency_ms": elapsed_ms,
        "quality_score": round(quality_score, 4),
        "structural_score": round(structural_score, 4),
        "score": case_score,
        "checks": checks,
        "passed": case_score >= 0.75 and all(checks.values()),
        "adaptation": result.get("adaptation"),
        "memory": result.get("memory"),
    }


async def run(base_url: str, suite_path: Path, timeout: float) -> dict[str, Any]:
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    api_key = os.getenv("ORBYTHRA_BENCHMARK_API_KEY", "").strip()
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for case in suite["cases"]:
            try:
                results.append(await _run_case(client, base_url, case, headers))
            except Exception as exc:
                results.append(
                    {
                        "id": case.get("id"),
                        "language": case.get("language"),
                        "score": 0.0,
                        "passed": False,
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:500],
                    }
                )
    scores = [float(item.get("score", 0.0)) for item in results]
    latencies = [float(item["latency_ms"]) for item in results if "latency_ms" in item]
    passed = sum(1 for item in results if item.get("passed"))
    overall = statistics.mean(scores) if scores else 0.0
    policy = suite.get("pass_policy") or {}
    return {
        "suite": suite.get("suite"),
        "base_url": base_url,
        "case_count": len(results),
        "passed_cases": passed,
        "pass_rate": round(passed / max(1, len(results)), 4),
        "overall_score": round(overall, 4),
        "median_latency_ms": round(statistics.median(latencies), 1) if latencies else None,
        "minimum_overall_score": policy.get("minimum_overall_score", 0.75),
        "suite_passed": (
            overall >= float(policy.get("minimum_overall_score", 0.75))
            and passed == len(results)
        ),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ORBYTHRA Adaptive Cognition live benchmark")
    parser.add_argument("--base-url", default=os.getenv("ORBYTHRA_BENCHMARK_BASE_URL", ""))
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.base_url:
        parser.error("--base-url or ORBYTHRA_BENCHMARK_BASE_URL is required")
    payload = asyncio.run(run(args.base_url, args.suite, args.timeout))
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if payload["suite_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
