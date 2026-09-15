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


async def _run_case(page: Any, base_url: str, case: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
    case_id = str(case.get("id") or "").split("-", 1)[0].upper()
    if not case_id.startswith("SV"):
        raise ValueError(f"Invalid strategic validation case id: {case_id}")

    started = time.perf_counter()
    await page.goto(f"{base_url.rstrip('/')}/#benchmark={case_id}", wait_until="domcontentloaded", timeout=timeout_ms)
    locator = page.locator('#orbythra-benchmark-json')
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
        "adaptation": result.get("adaptation"),
        "memory": result.get("memory"),
        "benchmark_boundary": benchmark,
    }


async def run(base_url: str, suite_path: Path, timeout: float) -> dict[str, Any]:
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []
    timeout_ms = int(timeout * 1000)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            for case in suite["cases"]:
                page = await browser.new_page(viewport={"width": 1280, "height": 800})
                try:
                    results.append(await _run_case(page, base_url, case, timeout_ms))
                except Exception as exc:
                    results.append(
                        {
                            "id": case.get("id"),
                            "language": case.get("language"),
                            "score": 0.0,
                            "passed": False,
                            "error_type": type(exc).__name__,
                            "error": str(exc)[:1000],
                        }
                    )
                finally:
                    await page.close()
        finally:
            await browser.close()

    scores = [float(item.get("score", 0.0)) for item in results]
    latencies = [float(item["latency_ms"]) for item in results if "latency_ms" in item]
    passed = sum(1 for item in results if item.get("passed"))
    overall = statistics.mean(scores) if scores else 0.0
    policy = suite.get("pass_policy") or {}
    minimum = float(policy.get("minimum_overall_score", 0.8))
    return {
        "suite": suite.get("suite"),
        "transport": "real-chromium-first-party-app-client",
        "base_url": base_url,
        "browser_entry": "/#benchmark=<SVxx>",
        "case_count": len(results),
        "executed_cases": len(results),
        "skipped_cases": 0,
        "passed_cases": passed,
        "pass_rate": round(passed / max(1, len(results)), 4),
        "overall_score": round(overall, 4),
        "median_latency_ms": round(statistics.median(latencies), 1) if latencies else None,
        "minimum_overall_score": minimum,
        "suite_passed": overall >= minimum and passed == len(results),
        "claim_boundary": (
            "First-party end-to-end live production benchmark executed through real Chromium, "
            "the public ORBYTHRA frontend, AppDeploy client transport, backend AI/tool loop and rendered result. "
            "It is not an independent OpenAI, Anthropic, academic, security, or AGI certification."
        ),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ORBYTHRA browser-driven strategic validation")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = asyncio.run(run(args.base_url, args.suite, args.timeout))
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if payload["suite_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
