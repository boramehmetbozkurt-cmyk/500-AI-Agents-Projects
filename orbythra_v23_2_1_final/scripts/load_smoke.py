from __future__ import annotations

import argparse
import concurrent.futures
import json
import time
import urllib.request


def one(url: str, api_key: str, workspace: str) -> tuple[int, float]:
    payload = json.dumps({"query": "Production load smoke verification"}).encode("utf-8")
    request = urllib.request.Request(
        url.rstrip("/") + "/v1/plan",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": api_key,
            "X-Workspace-ID": workspace,
        },
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response.read()
            status = response.status
    except Exception:
        status = 0
    return status, (time.perf_counter() - started) * 1000


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--requests", type=int, default=50)
    parser.add_argument("--concurrency", type=int, default=5)
    args = parser.parse_args()

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        results = list(pool.map(lambda _: one(args.url, args.api_key, "load-smoke"), range(args.requests)))
    ok = sum(status == 200 for status, _ in results)
    latencies = [latency for status, latency in results if status == 200]
    p95 = sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)] if latencies else 0.0
    print(json.dumps({"requests": args.requests, "ok": ok, "success_rate": ok / max(1, args.requests), "p95_ms": round(p95, 2)}))
    return 0 if ok == args.requests else 1


if __name__ == "__main__":
    raise SystemExit(main())
