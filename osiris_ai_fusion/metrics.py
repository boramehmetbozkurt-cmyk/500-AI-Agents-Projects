from __future__ import annotations

import threading
from collections import Counter, defaultdict, deque
from typing import Any


class Metrics:
    def __init__(self, sample_limit: int = 5000) -> None:
        self._counter: Counter[str] = Counter()
        self._samples: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=sample_limit))
        self._lock = threading.Lock()

    def inc(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counter[name] += amount

    def observe(self, name: str, value: float) -> None:
        with self._lock:
            self._samples[name].append(float(value))

    def counters(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counter)

    def summary(self, name: str) -> dict[str, float | int | None]:
        with self._lock:
            values = sorted(self._samples.get(name, ()))
        if not values:
            return {"count": 0, "min": None, "p50": None, "p95": None, "p99": None, "max": None}

        def percentile(p: float) -> float:
            index = min(len(values) - 1, max(0, round((len(values) - 1) * p)))
            return round(values[index], 3)

        return {
            "count": len(values),
            "min": round(values[0], 3),
            "p50": percentile(0.50),
            "p95": percentile(0.95),
            "p99": percentile(0.99),
            "max": round(values[-1], 3),
        }

    def slo_report(
        self,
        *,
        availability_target: float = 99.5,
        p95_latency_target_ms: float = 1500.0,
        minimum_requests: int = 20,
    ) -> dict[str, Any]:
        counters = self.counters()
        response_counts = {
            key: value for key, value in counters.items() if key.startswith("http_") and key[5:].isdigit()
        }
        total = sum(response_counts.values())
        server_errors = sum(
            value for key, value in response_counts.items() if 500 <= int(key[5:]) <= 599
        )
        availability = 100.0 if total == 0 else 100.0 * (total - server_errors) / total
        latency = self.summary("http_latency_ms")
        p95 = latency["p95"]
        enough_data = total >= minimum_requests
        availability_ok = availability >= availability_target
        latency_ok = p95 is None or float(p95) <= p95_latency_target_ms
        status = "insufficient_data"
        if enough_data:
            status = "pass" if availability_ok and latency_ok else "breach"
        return {
            "status": status,
            "window": "process_lifetime_bounded_samples",
            "requests": total,
            "server_errors": server_errors,
            "availability_percent": round(availability, 4),
            "latency_ms": latency,
            "targets": {
                "availability_percent": availability_target,
                "p95_latency_ms": p95_latency_target_ms,
                "minimum_requests": minimum_requests,
            },
            "checks": {
                "availability": availability_ok,
                "p95_latency": latency_ok,
                "sample_size": enough_data,
            },
        }

    def render_prometheus(self) -> str:
        lines = ["# TYPE orbythra_counter counter"]
        with self._lock:
            counter_items = sorted(self._counter.items())
        for name, value in counter_items:
            safe = name.replace("-", "_").replace(".", "_")
            lines.append(f'orbythra_counter{{name="{safe}"}} {value}')

        latency = self.summary("http_latency_ms")
        lines.append("# TYPE orbythra_http_latency_ms summary")
        for quantile, field in (("0.5", "p50"), ("0.95", "p95"), ("0.99", "p99")):
            value = latency[field]
            if value is not None:
                lines.append(
                    f'orbythra_http_latency_ms{{quantile="{quantile}"}} {float(value):.3f}'
                )
        lines.append(f'orbythra_http_latency_ms_count {int(latency["count"])}')
        return "\n".join(lines) + "\n"


metrics = Metrics()
