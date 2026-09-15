"""Normalize every provider and AI-research payload into one evidence schema.

Provider federation, the OSIRIS feeds and the AI Research Council each answer in
their own shape, and until now the only thing downstream consumers shared was the
per-tool wrapper in ``provenance.make_evidence_record``. The actual sources lived
inside opaque ``data`` blobs, so the same article fetched by three providers was
three unrelated blobs, and nothing ranked them.

This module extracts citable sources out of any payload, merges the ones that
resolve to the same canonical URL, and scores them with a transparent, inspectable
formula. Every item carries ``score_reasons`` so a reader can see why a source
ranked where it did; nothing here infers facts, it only organizes provenance.
"""

from __future__ import annotations

import hashlib
import time
from datetime import datetime
from functools import lru_cache
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from schemas import EvidenceItem

URL_KEYS = ("url", "uri", "link", "source_url", "html_url", "permalink")
TITLE_KEYS = ("title", "name", "headline", "label", "display_name", "place")
SNIPPET_KEYS = ("snippet", "summary", "description", "abstract", "text", "content", "answer")
TIME_KEYS = (
    "published_at", "published", "pubdate", "date", "timestamp", "time",
    "datetime", "updated", "updated_at", "created_at",
)

# Campaign/analytics parameters change per referral but never change the document,
# so they must not split one source into several.
TRACKING_PARAMS = frozenset(
    {
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id",
        "fbclid", "gclid", "gbraid", "wbraid", "msclkid", "mc_cid", "mc_eid",
        "igshid", "ref", "ref_src", "referrer", "source", "spm", "cmpid", "ncid",
    }
)

# A provider result wraps its content in an envelope. Those keys describe the
# fetch, not a document: source_url is the API endpoint we called, and treating it
# as a citable source turns every provider into a fake extra "source".
ENVELOPE_METADATA_KEYS = frozenset(
    {"source_url", "provider_id", "provider", "model", "domains", "freshness", "ok", "error"}
)

MAX_WALK_DEPTH = 8
MAX_ITEMS_PER_PAYLOAD = 400
DEFAULT_LIMIT = 120

# Score weights. They sum to 1.0 and are deliberately visible rather than tuned
# behind a model, because a research tool has to be able to defend its ordering.
WEIGHT_AUTHORITY = 0.45
WEIGHT_CORROBORATION = 0.30
WEIGHT_FRESHNESS = 0.20
WEIGHT_ADDRESSABLE = 0.05

DAY = 86_400


def parse_timestamp(value: Any) -> int | None:
    """Best-effort epoch seconds from an epoch number or an ISO-8601 string."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = int(value)
        # Providers mix seconds and milliseconds; anything past ~2286 is millis.
        return number // 1000 if number > 10_000_000_000 else number
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        if candidate.isdigit():
            return parse_timestamp(int(candidate))
        try:
            return int(datetime.fromisoformat(candidate.replace("Z", "+00:00")).timestamp())
        except ValueError:
            return None
    return None


def canonical_url(value: Any) -> str | None:
    """Collapse the spellings of one document into a single comparable URL."""
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate.lower().startswith(("http://", "https://")):
        return None
    try:
        parts = urlsplit(candidate)
    except ValueError:
        return None
    if not parts.hostname:
        return None

    host = parts.hostname.lower()
    if host.startswith("www."):
        host = host[4:]
    netloc = host
    if parts.port and parts.port not in (80, 443):
        netloc = f"{host}:{parts.port}"

    query = urlencode(
        sorted(
            (key, val)
            for key, val in parse_qsl(parts.query, keep_blank_values=True)
            if key.lower() not in TRACKING_PARAMS
        )
    )
    path = parts.path.rstrip("/") or "/"
    # http and https of the same document are the same document.
    return urlunsplit(("https", netloc, path, query, ""))


def domain_of(url: str | None) -> str | None:
    if not url:
        return None
    host = urlsplit(url).hostname
    return host.lower() if host else None


@lru_cache(maxsize=1)
def _provider_priorities() -> dict[str, int]:
    """Authority weights come from the provider registry, imported lazily.

    Keeping the import inside the function leaves this module free of httpx and
    the research-council stack, so normalization stays cheap to test.
    """
    try:
        from providers import BUILTIN_PROVIDERS

        return {spec.provider_id: spec.priority for spec in BUILTIN_PROVIDERS.values()}
    except Exception:
        return {}


def _first_str(row: dict[str, Any], keys: tuple[str, ...], *, limit: int) -> str:
    for key in keys:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:limit]
    return ""


def _first_timestamp(row: dict[str, Any]) -> int | None:
    for key in TIME_KEYS:
        if key in row:
            parsed = parse_timestamp(row[key])
            if parsed is not None:
                return parsed
    return None


def extract_source_items(payload: Any) -> list[dict[str, Any]]:
    """Pull every dict that names a fetchable source out of an arbitrary payload."""
    found: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    def walk(node: Any, depth: int) -> None:
        if depth > MAX_WALK_DEPTH or len(found) >= MAX_ITEMS_PER_PAYLOAD:
            return
        if isinstance(node, dict):
            lowered = {str(key).lower(): value for key, value in node.items()}
            raw_url = next(
                (lowered[key] for key in URL_KEYS if isinstance(lowered.get(key), str)),
                None,
            )
            url = canonical_url(raw_url)
            if url and url not in seen_urls:
                seen_urls.add(url)
                found.append(
                    {
                        "url": url,
                        "title": _first_str(lowered, TITLE_KEYS, limit=400) or url,
                        "snippet": _first_str(lowered, SNIPPET_KEYS, limit=1200),
                        "published_at": _first_timestamp(lowered),
                    }
                )
            for child in node.values():
                walk(child, depth + 1)
        elif isinstance(node, list):
            for child in node:
                walk(child, depth + 1)

    walk(payload, 0)
    return found


def _origins(record_data: Any) -> list[tuple[str | None, Any]]:
    """Split a tool payload into (provider_id, payload) pairs.

    Provider federation returns a ``results`` list where each entry names the
    provider or research engine that produced it, which is what authority and
    corroboration scoring needs. Anything else is treated as a single payload
    attributed to the tool itself.
    """
    if isinstance(record_data, dict):
        results = record_data.get("results")
        if isinstance(results, list) and results:
            pairs: list[tuple[str | None, Any]] = []
            for entry in results:
                if isinstance(entry, dict):
                    provider_id = entry.get("provider_id")
                    content = {
                        key: value
                        for key, value in entry.items()
                        if key not in ENVELOPE_METADATA_KEYS
                    }
                    pairs.append((
                        str(provider_id) if isinstance(provider_id, str) else None,
                        content,
                    ))
            if pairs:
                return pairs
    return [(None, record_data)]


def _freshness_component(published_at: int | None, now: int) -> tuple[float, str]:
    if published_at is None:
        # Unknown age is not the same as stale; neither reward nor punish it.
        return 0.25, "publication date unknown"
    age = max(0, now - published_at)
    if age <= 2 * DAY:
        return 1.0, "published within 2 days"
    if age <= 7 * DAY:
        return 0.8, "published within a week"
    if age <= 30 * DAY:
        return 0.5, "published within a month"
    if age <= 365 * DAY:
        return 0.2, "published within a year"
    return 0.0, "older than a year"


def _score(item: dict[str, Any], now: int) -> tuple[float, list[str]]:
    reasons: list[str] = []
    priorities = _provider_priorities()
    origins = item["providers"] or item["tools"]
    authority_raw = max((priorities.get(origin, 50) for origin in origins), default=50)
    authority = min(100, max(0, authority_raw)) / 100
    reasons.append(f"provider authority {authority_raw}/100")

    distinct = item["corroboration"]
    corroboration = min(distinct - 1, 3) / 3
    if distinct > 1:
        reasons.append(f"corroborated by {distinct} independent origins")
    else:
        reasons.append("single origin")

    freshness, freshness_reason = _freshness_component(item["published_at"], now)
    reasons.append(freshness_reason)

    addressable = 1.0 if item["url"] else 0.0
    if not addressable:
        reasons.append("no resolvable URL")

    score = (
        WEIGHT_AUTHORITY * authority
        + WEIGHT_CORROBORATION * corroboration
        + WEIGHT_FRESHNESS * freshness
        + WEIGHT_ADDRESSABLE * addressable
    )
    return round(min(1.0, max(0.0, score)), 4), reasons


def normalize_evidence(
    evidence: dict[str, Any],
    *,
    limit: int = DEFAULT_LIMIT,
    now: int | None = None,
) -> list[EvidenceItem]:
    """Merge every payload in an evidence bundle into ranked, deduplicated sources."""
    now = int(time.time()) if now is None else now
    merged: dict[str, dict[str, Any]] = {}

    for tool, record in sorted(evidence.items()):
        if not isinstance(record, dict) or record.get("ok") is not True:
            continue
        evidence_id = str(record.get("evidence_id") or "")
        for provider_id, payload in _origins(record.get("data")):
            for raw in extract_source_items(payload):
                key = raw["url"] or f"title::{tool}::{raw['title'].lower()}"
                slot = merged.get(key)
                if slot is None:
                    slot = {
                        "url": raw["url"],
                        "title": raw["title"],
                        "snippet": raw["snippet"],
                        "published_at": raw["published_at"],
                        "tools": [],
                        "providers": [],
                        "evidence_ids": [],
                        "origins": set(),
                    }
                    merged[key] = slot
                else:
                    # Keep the richest description and the earliest known date.
                    if len(raw["snippet"]) > len(slot["snippet"]):
                        slot["snippet"] = raw["snippet"]
                    if slot["published_at"] is None:
                        slot["published_at"] = raw["published_at"]
                if tool not in slot["tools"]:
                    slot["tools"].append(tool)
                if provider_id and provider_id not in slot["providers"]:
                    slot["providers"].append(provider_id)
                if evidence_id and evidence_id not in slot["evidence_ids"]:
                    slot["evidence_ids"].append(evidence_id)
                slot["origins"].add(provider_id or tool)

    items: list[EvidenceItem] = []
    for key, slot in merged.items():
        slot["corroboration"] = len(slot["origins"])
        score, reasons = _score(slot, now)
        items.append(
            EvidenceItem(
                item_id="src_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16],
                title=slot["title"][:400],
                url=slot["url"],
                domain=domain_of(slot["url"]),
                snippet=slot["snippet"][:1200],
                published_at=slot["published_at"],
                tools=slot["tools"][:24],
                providers=slot["providers"][:24],
                evidence_ids=slot["evidence_ids"][:24],
                corroboration=slot["corroboration"],
                score=score,
                score_reasons=reasons[:8],
            )
        )

    # Ties break on corroboration, then recency, then title, so the order is stable
    # across runs rather than dependent on dict iteration.
    items.sort(
        key=lambda item: (
            -item.score,
            -item.corroboration,
            -(item.published_at or 0),
            item.title.lower(),
        )
    )
    return items[:limit]


def compact_sources(items: list[EvidenceItem], *, limit: int = 40) -> list[dict[str, Any]]:
    """Prompt-sized projection: what the analyst needs to cite, nothing more."""
    return [
        {
            "item_id": item.item_id,
            "title": item.title,
            "url": item.url,
            "snippet": item.snippet[:400],
            "published_at": item.published_at,
            "corroboration": item.corroboration,
            "score": item.score,
            "evidence_ids": item.evidence_ids,
        }
        for item in items[:limit]
    ]
