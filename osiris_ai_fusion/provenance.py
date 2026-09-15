from __future__ import annotations

import hashlib
import json
import time
from typing import Any


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def make_evidence_record(
    *,
    tool: str,
    source_url: str,
    data: Any | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    fetched_at = int(time.time())
    evidence_id = "ev_" + hashlib.sha256(
        f"{tool}|{source_url}|{fetched_at}".encode("utf-8")
    ).hexdigest()[:16]
    body = {
        "evidence_id": evidence_id,
        "tool": tool,
        "source_url": source_url,
        "fetched_at": fetched_at,
        "ok": error is None,
        "data": data if error is None else None,
        "error": error,
    }
    body["digest"] = sha256_hex(body)
    return body


def evidence_bundle_digest(evidence: dict[str, Any]) -> str:
    stable = {
        key: {
            "evidence_id": value.get("evidence_id"),
            "tool": value.get("tool"),
            "source_url": value.get("source_url"),
            "fetched_at": value.get("fetched_at"),
            "ok": value.get("ok"),
            "digest": value.get("digest"),
        }
        for key, value in sorted(evidence.items())
    }
    return sha256_hex(stable)


def confidence_from_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    total = len(evidence)
    successes = sum(1 for value in evidence.values() if value.get("ok") is True)
    failures = total - successes
    score = round(successes / total, 3) if total else 0.0
    label = "high" if score >= 0.8 else "medium" if score >= 0.5 else "low"
    return {
        "score": score,
        "label": label,
        "successful_sources": successes,
        "failed_sources": failures,
        "total_sources": total,
        "method": "source-availability score; claim confidence is reported separately",
    }


def public_evidence_index(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "evidence_id": record.get("evidence_id"),
            "tool": record.get("tool"),
            "source_url": record.get("source_url"),
            "fetched_at": record.get("fetched_at"),
            "ok": record.get("ok"),
            "digest": record.get("digest"),
            "error": record.get("error"),
        }
        for record in evidence.values()
    ]
