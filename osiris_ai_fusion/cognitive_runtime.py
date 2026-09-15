from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
from datetime import UTC, datetime
from typing import Any

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _looks_turkish(text: str) -> bool:
    lowered = text.lower()
    markers = (" nedir", " kimdir", " nerede", " nasıl", " neden", " tarih", " hakkında", " türkiye", " izmir")
    return any(marker in f" {lowered}" for marker in markers) or any(ch in lowered for ch in "çğıöşü")


def _is_technical_query(text: str) -> bool:
    lowered = text.lower()
    terms = (
        "architecture", "mimari", "diagram", "şema", "system", "sistem", "engine", "motor",
        "chip", "gpu", "cpu", "robot", "satellite", "uydu", "network", "ağ", "blockchain",
        "ai", "agi", "model", "engineering", "mühendislik", "technical", "teknik",
    )
    return any(term in lowered for term in terms)


def _epoch_to_iso(value: Any) -> str | None:
    try:
        ts = int(value)
    except (TypeError, ValueError):
        return None
    try:
        return datetime.fromtimestamp(ts, tz=UTC).date().isoformat()
    except (OSError, OverflowError, ValueError):
        return None


async def _wikipedia_entity_enrichment(query: str) -> dict[str, Any]:
    """Resolve a likely entity to coordinates and a representative public image."""

    language_order = ["tr", "en"] if _looks_turkish(query) else ["en", "tr"]
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": query,
        "gsrlimit": "3",
        "prop": "coordinates|pageimages|info",
        "piprop": "thumbnail",
        "pithumbsize": "1000",
        "inprop": "url",
        "format": "json",
        "origin": "*",
    }
    timeout = httpx.Timeout(6.0, connect=3.0)
    best_visuals: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for lang in language_order:
            try:
                response = await client.get(f"https://{lang}.wikipedia.org/w/api.php", params=params)
                response.raise_for_status()
                payload = response.json()
            except Exception:
                continue
            pages = list((payload.get("query") or {}).get("pages", {}).values())
            if not pages:
                continue
            pages.sort(key=lambda row: int(row.get("index", 999999)))
            markers: list[dict[str, Any]] = []
            visuals: list[dict[str, Any]] = []
            for page in pages:
                title = str(page.get("title") or query)[:300]
                source_url = str(page.get("fullurl") or "") or None
                coords = page.get("coordinates") or []
                if coords:
                    coord = coords[0]
                    try:
                        markers.append(
                            {
                                "lat": float(coord["lat"]),
                                "lon": float(coord["lon"]),
                                "label": title,
                                "tool": f"wikipedia_{lang}",
                                "source_url": source_url,
                                "source_title": title,
                            }
                        )
                    except (KeyError, TypeError, ValueError):
                        pass
                thumb = page.get("thumbnail") or {}
                image_url = str(thumb.get("source") or "")
                if image_url:
                    visuals.append(
                        {
                            "title": title,
                            "url": image_url,
                            "thumbnail_url": image_url,
                            "source_url": source_url,
                            "provider": f"wikipedia_{lang}",
                            "kind": "technical_reference" if _is_technical_query(query) else "entity_reference",
                        }
                    )
            if visuals and not best_visuals:
                best_visuals = visuals[:6]
            if markers:
                return {"map_markers": markers[:8], "visual_assets": visuals[:6] or best_visuals}
    return {"map_markers": [], "visual_assets": best_visuals}


def _marker_key(row: dict[str, Any]) -> tuple[float, float, str] | None:
    if row.get("lat") is None or row.get("lon") is None:
        return None
    try:
        return (
            round(float(row["lat"]), 5),
            round(float(row["lon"]), 5),
            str(row.get("label", "")),
        )
    except (TypeError, ValueError):
        return None


async def enrich_research_context(
    query: str,
    evidence_items: list[dict[str, Any]],
    existing_markers: list[dict[str, Any]],
) -> dict[str, Any]:
    entity = await _wikipedia_entity_enrichment(query)
    markers = list(existing_markers)
    seen = {key for row in markers if (key := _marker_key(row)) is not None}
    for row in entity["map_markers"]:
        key = _marker_key(row)
        if key is not None and key not in seen:
            seen.add(key)
            markers.append(row)

    source_timeline = []
    for item in evidence_items:
        date = _epoch_to_iso(item.get("published_at"))
        if not date:
            continue
        source_timeline.append(
            {
                "date": date,
                "title": str(item.get("title") or "Source event")[:300],
                "summary": str(item.get("snippet") or "")[:900],
                "evidence_ids": list(item.get("evidence_ids") or [])[:12],
                "source_url": item.get("url"),
            }
        )
    source_timeline.sort(key=lambda row: row["date"])

    return {
        "map_markers": markers[:200],
        "visual_assets": entity["visual_assets"],
        "source_timeline": source_timeline[:40],
        "digital_map": {
            "enabled": True,
            "marker_count": len(markers),
            "mode": "evidence-first-geospatial-context",
        },
    }


async def resolve_timeline_locations(
    report: dict[str, Any],
    existing_markers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach geospatial context to timeline locations without inventing coordinates."""

    labels: list[str] = []
    event_by_label: dict[str, dict[str, Any]] = {}
    for event in report.get("historical_timeline") or []:
        label = str(event.get("location_label") or "").strip()
        if not label or label in event_by_label:
            continue
        labels.append(label)
        event_by_label[label] = event
        if len(labels) >= 6:
            break
    if not labels:
        return existing_markers

    resolved = await asyncio.gather(*(_wikipedia_entity_enrichment(label) for label in labels))
    markers = list(existing_markers)
    seen = {key for row in markers if (key := _marker_key(row)) is not None}
    for label, payload in zip(labels, resolved, strict=True):
        event = event_by_label[label]
        for row in payload.get("map_markers", [])[:2]:
            enriched = dict(row)
            enriched["label"] = f"{event.get('date', '')} · {event.get('title', label)}"
            enriched["timestamp"] = event.get("date")
            refs = event.get("evidence_ids") or []
            if refs:
                enriched["evidence_id"] = refs[0]
            key = _marker_key(enriched)
            if key is not None and key not in seen:
                seen.add(key)
                markers.append(enriched)
    return markers[:200]


def _load_aes_key() -> bytes | None:
    raw = os.getenv("ORBYTHRA_AES256_KEY_B64", "").strip()
    if not raw:
        return None
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception as exc:
        raise ValueError("ORBYTHRA_AES256_KEY_B64 must be valid base64") from exc
    if len(key) != 32:
        raise ValueError("ORBYTHRA_AES256_KEY_B64 must decode to exactly 32 bytes")
    return key


def build_secure_capsule(payload: dict[str, Any]) -> dict[str, Any]:
    """Create an encrypted portable investigation capsule when the deployment key exists.

    The existing SEAL/Ed25519 receipt protects intent and integrity. This capsule adds
    confidentiality for export/archive using AES-256-GCM. No secret key is returned.
    """

    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    key = _load_aes_key()
    if key is None:
        return {
            "enabled": False,
            "algorithm": "AES-256-GCM",
            "integrity_sha256": digest,
            "reason": "ORBYTHRA_AES256_KEY_B64 is not configured",
            "seal_layer": "canonical-CBOR + domain-separated SHA-256 + optional Ed25519 receipt",
        }
    nonce = os.urandom(12)
    aad = b"ORBYTHRA-RESEARCH-CAPSULE-V1"
    ciphertext = AESGCM(key).encrypt(nonce, canonical, aad)
    return {
        "enabled": True,
        "algorithm": "AES-256-GCM",
        "aad": aad.decode("ascii"),
        "nonce_b64": base64.b64encode(nonce).decode("ascii"),
        "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
        "integrity_sha256": digest,
        "seal_layer": "canonical-CBOR + domain-separated SHA-256 + optional Ed25519 receipt",
    }
