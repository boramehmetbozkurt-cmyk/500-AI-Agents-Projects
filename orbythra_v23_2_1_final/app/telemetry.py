from __future__ import annotations

import json
import os
import queue
import re
import secrets
import threading
import time
import urllib.error
import urllib.request
from collections import Counter, deque
from dataclasses import dataclass
from typing import Any

_TRACEPARENT_RE = re.compile(r"^[\da-f]{2}-([\da-f]{32})-([\da-f]{16})-([\da-f]{2})$", re.IGNORECASE)


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._requests = Counter()
        self._latency_ms_total = 0.0
        self._request_total = 0

    def observe(self, method: str, path: str, status_code: int, latency_ms: float) -> None:
        key = f"{method} {path} {status_code}"
        with self._lock:
            self._requests[key] += 1
            self._latency_ms_total += latency_ms
            self._request_total += 1

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            avg = self._latency_ms_total / self._request_total if self._request_total else 0.0
            return {
                "request_total": self._request_total,
                "average_latency_ms": round(avg, 3),
                "requests": dict(self._requests),
                "generated_at": int(time.time()),
            }


@dataclass(frozen=True)
class TraceContext:
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    trace_flags: str = "01"

    @property
    def traceparent(self) -> str:
        return f"00-{self.trace_id}-{self.span_id}-{self.trace_flags}"


class OtlpHttpJsonTelemetry:
    """Dependency-free W3C Trace Context + opt-in OTLP/HTTP JSON exporter."""

    def __init__(self) -> None:
        self.endpoint = os.getenv("ORBYTHRA_OTLP_ENDPOINT", "").strip().rstrip("/")
        self.service_name = os.getenv("ORBYTHRA_OTLP_SERVICE_NAME", "orbythra").strip() or "orbythra"
        self.headers = self._parse_headers(os.getenv("ORBYTHRA_OTLP_HEADERS", ""))
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1000)
        self._recent: deque[dict[str, Any]] = deque(maxlen=256)
        self._lock = threading.RLock()
        self._exported = 0
        self._failed = 0
        self._dropped = 0
        if self.enabled:
            threading.Thread(target=self._worker, name="orbythra-otlp", daemon=True).start()

    @property
    def enabled(self) -> bool:
        return self.endpoint.startswith(("http://", "https://"))

    @staticmethod
    def _parse_headers(raw: str) -> dict[str, str]:
        headers: dict[str, str] = {}
        for item in raw.split(","):
            if "=" not in item:
                continue
            key, value = item.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key and value:
                headers[key] = value
        return headers

    def begin(self, traceparent: str | None = None) -> TraceContext:
        if traceparent:
            match = _TRACEPARENT_RE.fullmatch(traceparent.strip())
            if match:
                trace_id, parent_span_id, flags = (part.lower() for part in match.groups())
                if trace_id != "0" * 32 and parent_span_id != "0" * 16 and flags in {"00", "01"}:
                    return TraceContext(
                        trace_id=trace_id,
                        span_id=secrets.token_hex(8),
                        parent_span_id=parent_span_id,
                        trace_flags=flags,
                    )
        return TraceContext(trace_id=secrets.token_hex(16), span_id=secrets.token_hex(8), trace_flags="01")

    @staticmethod
    def _attr(key: str, value: Any) -> dict[str, Any]:
        if isinstance(value, bool):
            mapped = {"boolValue": value}
        elif isinstance(value, int):
            mapped = {"intValue": str(value)}
        elif isinstance(value, float):
            mapped = {"doubleValue": value}
        else:
            mapped = {"stringValue": str(value)}
        return {"key": key, "value": mapped}

    def observe_http(
        self,
        context: TraceContext,
        *,
        method: str,
        path: str,
        status_code: int,
        request_id: str,
        start_time_unix_nano: int,
        end_time_unix_nano: int,
    ) -> None:
        attributes = [
            self._attr("http.request.method", method),
            self._attr("url.path", path),
            self._attr("http.response.status_code", status_code),
            self._attr("orbythra.request_id", request_id),
            self._attr("openinference.span.kind", "CHAIN"),
        ]
        span = {
            "traceId": context.trace_id,
            "spanId": context.span_id,
            "traceState": "",
            "name": f"{method} {path}",
            "kind": 2,
            "startTimeUnixNano": str(start_time_unix_nano),
            "endTimeUnixNano": str(max(end_time_unix_nano, start_time_unix_nano)),
            "attributes": attributes,
            "status": {"code": 1 if status_code < 500 else 2},
        }
        if context.parent_span_id:
            span["parentSpanId"] = context.parent_span_id
        payload = {
            "resourceSpans": [{
                "resource": {
                    "attributes": [
                        self._attr("service.name", self.service_name),
                        self._attr("service.version", "21"),
                    ]
                },
                "scopeSpans": [{
                    "scope": {"name": "orbythra.v21.telemetry", "version": "21"},
                    "spans": [span],
                }],
            }]
        }
        with self._lock:
            self._recent.append({
                "trace_id": context.trace_id,
                "span_id": context.span_id,
                "parent_span_id": context.parent_span_id,
                "method": method,
                "path": path,
                "status_code": status_code,
                "duration_ms": round((max(end_time_unix_nano, start_time_unix_nano) - start_time_unix_nano) / 1_000_000, 6),
            })
        if not self.enabled:
            return
        try:
            self._queue.put_nowait(payload)
        except queue.Full:
            with self._lock:
                self._dropped += 1

    def _target(self) -> str:
        return self.endpoint if self.endpoint.endswith("/v1/traces") else self.endpoint + "/v1/traces"

    def _worker(self) -> None:
        while True:
            payload = self._queue.get()
            try:
                body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
                headers = {"Content-Type": "application/json", **self.headers}
                request = urllib.request.Request(self._target(), data=body, headers=headers, method="POST")
                with urllib.request.urlopen(request, timeout=3.0) as response:
                    if int(getattr(response, "status", 200)) >= 400:
                        raise RuntimeError("otlp_export_rejected")
                with self._lock:
                    self._exported += 1
            except (OSError, urllib.error.URLError, RuntimeError, ValueError):
                with self._lock:
                    self._failed += 1
            finally:
                self._queue.task_done()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.enabled,
                "service_name": self.service_name,
                "queued": self._queue.qsize(),
                "exported": self._exported,
                "failed": self._failed,
                "dropped": self._dropped,
                "recent_spans": list(self._recent),
            }


METRICS = Metrics()
OTEL = OtlpHttpJsonTelemetry()
