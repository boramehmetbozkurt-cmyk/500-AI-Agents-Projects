from __future__ import annotations

import json
import statistics
import time
from datetime import UTC, datetime

from app.models import VerifyRequest
from app.services.evidence import verify


def run(iterations: int = 1000) -> dict[str, object]:
    request = VerifyRequest(
        claims=[{"id": "c1", "text": "supported claim", "evidence_ids": ["e1"], "time_sensitive": False}],
        evidence=[{"id": "e1", "support": 0.95, "authority": 0.95, "retrieved_at": "2026-09-29T00:00:00+00:00", "contradicts": False}],
        minimum_support=0.75,
        minimum_authority=0.60,
        max_age_days=30,
    )
    now = datetime(2026, 9, 30, tzinfo=UTC)
    samples: list[float] = []
    failures = 0
    for _ in range(iterations):
        started = time.perf_counter()
        result = verify(request, now=now)
        samples.append((time.perf_counter() - started) * 1000.0)
        if result.disposition != "ANSWER" or result.supported_claims != 1:
            failures += 1
    ordered = sorted(samples)
    p95 = ordered[max(0, min(len(ordered) - 1, int(len(ordered) * 0.95) - 1))]
    report = {
        "gate": "deterministic_verification_performance_smoke",
        "iterations": iterations,
        "failures": failures,
        "mean_ms": round(statistics.fmean(samples), 6),
        "p95_ms": round(p95, 6),
        "acceptance_p95_ms": 250.0,
        "passed": failures == 0 and p95 <= 250.0,
        "validation_boundary": "In-process CI microbenchmark only; not production network latency, capacity or SLA evidence.",
    }
    return report


if __name__ == "__main__":
    report = run()
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["passed"] else 1)
