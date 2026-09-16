from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

from run_adaptive_benchmark import _normalize_result, _requirement_checks

DEFAULT_SUITE = Path(__file__).resolve().parent / "benchmarks" / "strategic_ai_validation_v1.json"
BUDGET_ERROR_CODE = "ai_daily_token_budget_exceeded"


def _is_budget_block(message: str) -> bool:
    lowered = message.lower()
    return BUDGET_ERROR_CODE in lowered or "ai daily token budget exceeded" in lowered


async def _run_case(browser: Any, base_url: str, case: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
    case_id = str(case.get("id") or "").split("-", 1)[0].upper()
    if not case_id.startswith("SV"):
        raise ValueError(f"Invalid strategic validation case id: {case_id}")

    page = await browser.new_page(viewport={"width": 1280, "height": 800})
    started = time.perf_counter()
    try:
        await page.goto(
            f"{base_url.rstrip('/')}/#benchmark={case_id}",
            wait_until="domcontentloaded",
            timeout=timeout_ms,
        )
        locator = page.locator("#orbythra-benchmark-json")
        await locator.wait_for(state="visible", timeout=timeout_ms)
        await page.wait_for_function(
            """() => {
              const node = document.querySelector('#orbythra-benchmark-json');
              const status = node?.getAttribute('data-benchmark-status');
              return status === 'complete' || status === 'error';
            }""",
            timeout=timeout_ms,
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        status = await locator.get_attribute("data-benchmark-status")
        text = await locator.text_content()
        if not text:
            raise ValueError("Benchmark mode rendered no machine-readable payload")
        payload = json.loads(text)
        if status == "error" or payload.get("error"):
            raise RuntimeError(str(payload.get("error") or "browser benchmark failed"))

        benchmark = payload.get("benchmark") or {}
        if benchmark.get("id") != case_id or benchmark.get("fixedCase") is not True:
            raise ValueError("Live browser result did not attest a fixed benchmark case")
        if benchmark.get("memoryWrites") is not False or benchmark.get("externalSideEffects") is not False:
            raise ValueError("Benchmark safety boundary is not read-only")

        result = _normalize_result(payload)
        checks = _requirement_checks(list(case.get("requires") or []), result)
        evaluation = result.get("self_evaluation") or {}
        quality_score = float(evaluation.get("score", 0.0))
        structural_score = sum(checks.values()) / max(1, len(checks))
        case_score = round(0.7 * quality_score + 0.3 * structural_score, 4)
        return {
            "id": case["id"],
            "runtime_case_id": case_id,
            "language": case.get("language"),
            "latency_ms": elapsed_ms,
            "quality_score": round(quality_score, 4),
            "structural_score": round(structural_score, 4),
            "score": case_score,
            "checks": checks,
            "passed": case_score >= 0.75 and all(checks.values()),
            "blocked": False,
            "adaptation": result.get("adaptation"),
            "memory": result.get("memory"),
            "benchmark_boundary": benchmark,
        }
    except Exception as exc:
        message = str(exc)[:2000]
        budget_blocked = _is_budget_block(message)
        return {
            "id": case.get("id"),
            "runtime_case_id": case_id,
            "language": case.get("language"),
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "score": None if budget_blocked else 0.0,
            "passed": False,
            "blocked": budget_blocked,
            "block_reason": BUDGET_ERROR_CODE if budget_blocked else None,
            "error_type": type(exc).__name__,
            "error": message,
        }
    finally:
        await page.close()


async def run(
    base_url: str,
    suite_path: Path,
    timeout: float,
    concurrency: int,
) -> dict[str, Any]:
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    cases = list(suite["cases"])
    timeout_ms = int(timeout * 1000)
    effective_concurrency = max(1, min(5, concurrency))
    results: list[dict[str, Any]] = []

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            if effective_concurrency == 1:
                for index, case in enumerate(cases):
                    item = await _run_case(browser, base_url, case, timeout_ms)
                    results.append(item)
                    if item.get("blocked"):
                        for remaining in cases[index + 1 :]:
                            results.append(
                                {
                                    "id": remaining.get("id"),
                                    "runtime_case_id": str(remaining.get("id") or "").split("-", 1)[0].upper(),
                                    "language": remaining.get("language"),
                                    "skipped": True,
                                    "blocked": True,
                                    "block_reason": BUDGET_ERROR_CODE,
                                    "passed": False,
                                    "reason": "Not executed after the live runtime reported daily AI token budget exhaustion.",
                                }
                            )
                        break
            else:
                limit = asyncio.Semaphore(effective_concurrency)

                async def bounded(case: dict[str, Any]) -> dict[str, Any]:
                    async with limit:
                        return await _run_case(browser, base_url, case, timeout_ms)

                results = await asyncio.gather(*(bounded(case) for case in cases))
        finally:
            await browser.close()

    budget_blocked = any(item.get("blocked") for item in results)
    scored = [
        item
        for item in results
        if not item.get("skipped") and not item.get("blocked") and isinstance(item.get("score"), (int, float))
    ]
    executed = [item for item in results if not item.get("skipped")]
    scores = [float(item["score"]) for item in scored]
    latencies = [float(item["latency_ms"]) for item in executed if "latency_ms" in item]
    passed = sum(1 for item in scored if item.get("passed"))
    overall = statistics.mean(scores) if scores else None
    policy = suite.get("pass_policy") or {}
    minimum = float(policy.get("minimum_overall_score", 0.8))
    suite_passed = bool(
        not budget_blocked
        and len(scored) == len(cases)
        and overall is not None
        and overall >= minimum
        and passed == len(cases)
    )
    return {
        "suite": suite.get("suite"),
        "transport": "real-chromium-first-party-app-client",
        "base_url": base_url,
        "browser_entry": "/#benchmark=<SVxx>",
        "concurrency": effective_concurrency,
        "case_timeout_seconds": timeout,
        "case_count": len(results),
        "executed_cases": len(executed),
        "scored_cases": len(scored),
        "skipped_cases": sum(1 for item in results if item.get("skipped")),
        "passed_cases": passed,
        "pass_rate": round(passed / max(1, len(scored)), 4),
        "overall_score": round(overall, 4) if overall is not None else None,
        "median_latency_ms": round(statistics.median(latencies), 1) if latencies else None,
        "minimum_overall_score": minimum,
        "budget_blocked": budget_blocked,
        "block_reason": BUDGET_ERROR_CODE if budget_blocked else None,
        "suite_passed": suite_passed,
        "claim_boundary": (
            "First-party end-to-end live production benchmark executed through real Chromium, "
            "the public ORBYTHRA frontend, AppDeploy client transport, backend AI/tool loop and rendered result. "
            "A platform budget block is reported separately and is not scored as model-quality evidence. "
            "This is not an independent OpenAI, Anthropic, academic, security, or AGI certification."
        ),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ORBYTHRA browser-driven strategic validation")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = asyncio.run(run(args.base_url, args.suite, args.timeout, args.concurrency))
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if payload["suite_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
