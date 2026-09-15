from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(quantile * len(ordered)) - 1))
    return round(ordered[index], 3)


def _safe_target(base_url: str, path: str) -> tuple[str, str]:
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("base URL must be an absolute HTTP(S) URL")
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("production probes require HTTPS; HTTP is allowed only for localhost")
    normalized_path = "/" + path.lstrip("/")
    url = urljoin(base_url.rstrip("/") + "/", normalized_path.lstrip("/"))
    public_target = f"{parsed.scheme}://{parsed.netloc}{normalized_path}"
    return url, public_target


def _probe_once(url: str, headers: dict[str, str], timeout: float, expected_status: int) -> dict[str, Any]:
    started = time.perf_counter()
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - operator supplied owned target
            sample = response.read(4096)
            status = int(response.status)
            return {
                "ok": status == expected_status,
                "status": status,
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                "body_prefix_sha256": hashlib.sha256(sample).hexdigest(),
                "error_type": None,
            }
    except HTTPError as exc:
        return {
            "ok": exc.code == expected_status,
            "status": int(exc.code),
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "body_prefix_sha256": None,
            "error_type": type(exc).__name__,
        }
    except (URLError, TimeoutError, OSError) as exc:
        return {
            "ok": False,
            "status": None,
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "body_prefix_sha256": None,
            "error_type": type(exc).__name__,
        }


def run_probe(
    *,
    base_url: str,
    path: str = "/health",
    requests: int = 5,
    concurrency: int = 1,
    timeout: float = 10.0,
    expected_status: int = 200,
    api_key: str = "",
) -> dict[str, Any]:
    if requests < 1 or requests > 200:
        raise ValueError("requests must be between 1 and 200")
    if concurrency < 1 or concurrency > 10:
        raise ValueError("concurrency must be between 1 and 10")
    if concurrency > requests:
        concurrency = requests

    url, public_target = _safe_target(base_url, path)
    headers = {"User-Agent": "ORBYTHRA-Production-Evidence/1.0"}
    if api_key:
        headers["X-API-Key"] = api_key

    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [
            executor.submit(_probe_once, url, headers, timeout, expected_status)
            for _ in range(requests)
        ]
        samples = [future.result() for future in futures]

    latencies = [float(sample["latency_ms"]) for sample in samples]
    successes = sum(1 for sample in samples if sample["ok"])
    status_counts = Counter(str(sample["status"]) for sample in samples)
    error_counts = Counter(
        str(sample["error_type"]) for sample in samples if sample.get("error_type")
    )
    return {
        "schema": "orbythra.production-probe.v1",
        "product": "ORBYTHRA",
        "generated_at": _utc_now(),
        "git_sha": os.getenv("GITHUB_SHA", "unknown"),
        "production_measurement": True,
        "external_target": True,
        "target": public_target,
        "expected_status": expected_status,
        "requests": requests,
        "concurrency": concurrency,
        "successes": successes,
        "success_rate": round(successes / requests, 6),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "latency_ms": {
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "p99": percentile(latencies, 0.99),
            "max": round(max(latencies), 3) if latencies else None,
        },
        "status_counts": dict(sorted(status_counts.items())),
        "error_counts": dict(sorted(error_counts.items())),
        "samples": samples,
        "claim_boundary": (
            "One probe run is production evidence for this interval only. Uptime/SLO history requires "
            "retaining repeated runs over the stated diligence window."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect bounded ORBYTHRA production uptime/latency evidence")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--path", default="/health")
    parser.add_argument("--requests", type=int, default=5)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--expected-status", type=int, default=200)
    parser.add_argument("--api-key-env", default="ORBYTHRA_PRODUCTION_API_KEY")
    parser.add_argument("--output")
    parser.add_argument("--fail-below", type=float)
    args = parser.parse_args()

    result = run_probe(
        base_url=args.base_url,
        path=args.path,
        requests=args.requests,
        concurrency=args.concurrency,
        timeout=args.timeout,
        expected_status=args.expected_status,
        api_key=os.getenv(args.api_key_env, "").strip(),
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if args.fail_below is not None and result["success_rate"] < args.fail_below:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
