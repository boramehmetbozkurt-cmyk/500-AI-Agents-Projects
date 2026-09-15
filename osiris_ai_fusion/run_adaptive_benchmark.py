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
MEMORY_REQUIREMENTS = {"memory", "workspace_memory_only", "no_cross_tenant_recall"}


def _normalize_result(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize the Python core and AppDeploy runtime to one benchmark contract."""

    if isinstance(payload.get("report"), dict):
        return payload
    sources = payload.get("sources") or []
    timeline = payload.get("timeline") or []
    ideas = payload.get("ideas") or []
    markers = payload.get("mapMarkers") or []
    return {
        **payload,
        "report": {
            "bluf": payload.get("answer") or "",
            "claims": payload.get("claims") or [],
            "historical_timeline": timeline,
            "developed_ideas": ideas,
            "map_markers": markers,
            "spatial_summary": (
                f"Production runtime returned {len(markers)} server-resolved marker(s)."
                if markers
                else ""
            ),
            "data_gaps": payload.get("dataGaps") or [],
            "overall_confidence": payload.get("confidence") or 0.0,
        },
        "evidence_index": sources,
        "self_evaluation": payload.get("selfEvaluation") or {},
        "cognitive_plan": payload.get("cognitivePlan") or {},
        "adaptation": payload.get("adaptation") or {},
        "memory": payload.get("memory") or {},
        "planned_tools": payload.get("planned_tools") or [],
    }


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
        elif requirement in MEMORY_REQUIREMENTS:
            mode = str(memory.get("mode") or "")
            checks[requirement] = bool(memory.get("workspace_isolated")) or mode == "AUTHENTICATED"
        elif requirement in {"max_one_refinement", "no_new_tools_on_refinement", "bounded_autonomy"}:
            checks[requirement] = (
                int(adaptation.get("passes", 0)) <= 1
                and int(adaptation.get("external_tool_calls", adaptation.get("externalToolCalls", 0))) == 0
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
    api_path: str,
    case: dict[str, Any],
    headers: dict[str, str],
) -> dict[str, Any]:
    started = time.perf_counter()
    path = "/" + api_path.strip("/")
    response = await client.post(
        base_url.rstrip("/") + path,
        headers=headers,
        json={
            "query": case["query"],
            "save": False,
            "scope": {"workspace_id": "adaptive-benchmark"},
        },
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    response.raise_for_status()
    result = _normalize_result(response.json())
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


async def run(base_url: str, api_path: str, suite_path: Path, timeout: float) -> dict[str, Any]:
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    api_key = os.getenv("ORBYTHRA_BENCHMARK_API_KEY", "").strip()
    bearer = os.getenv("ORBYTHRA_BENCHMARK_BEARER_TOKEN", "").strip()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "ORBYTHRA-Strategic-Validation/1.0",
    }
    normalized_base = base_url.rstrip("/")
    if "appdeploy.ai" in normalized_base:
        # AppDeploy applies browser-origin CSRF protections to public POST routes.
        # The benchmark calls the same public route as the first-party web client,
        # so bind the request to the deployed app origin instead of bypassing auth.
        headers["Origin"] = normalized_base
        headers["Referer"] = normalized_base + "/"
    if api_key:
        headers["X-API-Key"] = api_key
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"

    results: list[dict[str, Any]] = []
    skipped = 0
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for case in suite["cases"]:
            requirements = set(case.get("requires") or [])
            if requirements.intersection(MEMORY_REQUIREMENTS) and not (api_key or bearer):
                results.append(
                    {
                        "id": case.get("id"),
                        "language": case.get("language"),
                        "skipped": True,
                        "passed": False,
                        "reason": "authenticated memory credential not configured",
                    }
                )
                skipped += 1
                continue
            try:
                results.append(await _run_case(client, base_url, api_path, case, headers))
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

    executed = [item for item in results if not item.get("skipped")]
    scores = [float(item.get("score", 0.0)) for item in executed]
    latencies = [float(item["latency_ms"]) for item in executed if "latency_ms" in item]
    passed = sum(1 for item in executed if item.get("passed"))
    overall = statistics.mean(scores) if scores else 0.0
    policy = suite.get("pass_policy") or {}
    return {
        "suite": suite.get("suite"),
        "base_url": base_url,
        "api_path": "/" + api_path.strip("/"),
        "case_count": len(results),
        "executed_cases": len(executed),
        "skipped_cases": skipped,
        "passed_cases": passed,
        "pass_rate": round(passed / max(1, len(executed)), 4),
        "overall_score": round(overall, 4),
        "median_latency_ms": round(statistics.median(latencies), 1) if latencies else None,
        "minimum_overall_score": policy.get("minimum_overall_score", 0.75),
        "suite_passed": (
            skipped == 0
            and overall >= float(policy.get("minimum_overall_score", 0.75))
            and passed == len(executed)
        ),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ORBYTHRA Adaptive Cognition live benchmark")
    parser.add_argument("--base-url", default=os.getenv("ORBYTHRA_BENCHMARK_BASE_URL", ""))
    parser.add_argument(
        "--api-path",
        default=os.getenv("ORBYTHRA_BENCHMARK_API_PATH", "/investigate"),
        help="Use /investigate for the Python core or /api/investigate for AppDeploy.",
    )
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.base_url:
        parser.error("--base-url or ORBYTHRA_BENCHMARK_BASE_URL is required")
    payload = asyncio.run(run(args.base_url, args.api_path, args.suite, args.timeout))
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if payload["suite_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
