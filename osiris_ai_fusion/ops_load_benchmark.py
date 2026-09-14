from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path
from typing import Any

import httpx


def _percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * p)))
    return round(ordered[index], 3)


async def run_load_benchmark(
    app: Any,
    *,
    requests: int = 100,
    concurrency: int = 10,
    path: str = "/health",
) -> dict[str, Any]:
    if requests < 1 or concurrency < 1:
        raise ValueError("requests and concurrency must be positive")
    semaphore = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    statuses: dict[int, int] = {}
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://orbythra.local") as client:
        async def one() -> None:
            async with semaphore:
                started = time.perf_counter()
                response = await client.get(path)
                elapsed = (time.perf_counter() - started) * 1000.0
                latencies.append(elapsed)
                statuses[response.status_code] = statuses.get(response.status_code, 0) + 1

        wall_started = time.perf_counter()
        await asyncio.gather(*(one() for _ in range(requests)))
        wall_seconds = time.perf_counter() - wall_started

    successful = sum(value for status, value in statuses.items() if 200 <= status < 400)
    return {
        "schema": "orbythra.load-benchmark.v1",
        "synthetic_local_asgi": True,
        "production_measurement": False,
        "path": path,
        "requests": requests,
        "concurrency": concurrency,
        "statuses": {str(key): value for key, value in sorted(statuses.items())},
        "success_rate": round(successful / requests, 4),
        "throughput_requests_per_second": round(requests / max(wall_seconds, 0.000001), 3),
        "latency_ms": {
            "min": round(min(latencies), 3),
            "mean": round(statistics.fmean(latencies), 3),
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
            "p99": _percentile(latencies, 0.99),
            "max": round(max(latencies), 3),
        },
        "note": (
            "This is an in-process ASGI regression baseline. Production SLO claims require "
            "external traffic and uptime measurements."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ORBYTHRA in-process load baseline")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--path", default="/health")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    from app import app

    result = asyncio.run(
        run_load_benchmark(
            app,
            requests=args.requests,
            concurrency=args.concurrency,
            path=args.path,
        )
    )
    rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
