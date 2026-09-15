from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from typing import Any

import httpx

from config import get_settings
from provenance import make_evidence_record
from source_policy import policy_for_tool


@dataclass(frozen=True)
class ToolSpec:
    name: str
    path: str
    domain: str
    description: str


TOOL_SPECS: dict[str, ToolSpec] = {
    "flights": ToolSpec("flights", "/api/flights", "aviation", "Live aircraft/flight feed."),
    "satellites": ToolSpec(
        "satellites", "/api/satellites", "space", "Satellite positions and metadata."
    ),
    "space_weather": ToolSpec(
        "space_weather", "/api/space-weather", "space", "Space-weather conditions."
    ),
    "earthquakes": ToolSpec("earthquakes", "/api/earthquakes", "seismic", "Earthquake events."),
    "fires": ToolSpec("fires", "/api/fires", "environment", "Wildfire/hotspot detections."),
    "weather": ToolSpec("weather", "/api/weather", "environment", "Weather observations/events."),
    "air_quality": ToolSpec(
        "air_quality", "/api/air-quality", "environment", "Air-quality conditions."
    ),
    "radar": ToolSpec("radar", "/api/radar", "environment", "Radar products."),
    "sentinel": ToolSpec(
        "sentinel", "/api/sentinel", "environment", "Sentinel-derived public observations."
    ),
    "conflicts": ToolSpec("conflicts", "/api/conflicts", "geopolitics", "Conflict-event feed."),
    "frontlines": ToolSpec(
        "frontlines", "/api/frontlines", "geopolitics", "Frontline/geopolitical layer."
    ),
    "gdelt": ToolSpec("gdelt", "/api/gdelt", "geopolitics", "GDELT global event/news signals."),
    "country_risk": ToolSpec(
        "country_risk", "/api/country-risk", "geopolitics", "Country-risk data."
    ),
    "region_dossier": ToolSpec(
        "region_dossier", "/api/region-dossier", "geopolitics", "Regional dossier data."
    ),
    "news": ToolSpec("news", "/api/news", "media", "News feed."),
    "live_news": ToolSpec("live_news", "/api/live-news", "media", "Live news feed."),
    "markets": ToolSpec("markets", "/api/markets", "markets", "Market indicators."),
    "crypto": ToolSpec("crypto", "/api/crypto", "markets", "Crypto-market data."),
    "scm_suppliers": ToolSpec(
        "scm_suppliers", "/api/scm-suppliers", "supply_chain", "Supply-chain supplier data."
    ),
    "cctv": ToolSpec("cctv", "/api/cctv", "infrastructure", "Public traffic-camera metadata."),
    "infrastructure": ToolSpec(
        "infrastructure", "/api/infrastructure", "infrastructure", "Infrastructure layer."
    ),
    "maritime": ToolSpec("maritime", "/api/maritime", "maritime", "Maritime/port/chokepoint feed."),
    "cyber_threats": ToolSpec(
        "cyber_threats", "/api/cyber-threats", "cyber", "Passive cyber-threat feed."
    ),
    "cyber_attacks": ToolSpec(
        "cyber_attacks", "/api/cyber-attacks", "cyber", "Passive cyber-attack telemetry."
    ),
    "malware": ToolSpec("malware", "/api/malware", "cyber", "Passive malware intelligence."),
}

READ_ONLY_TOOLS: dict[str, str] = {name: spec.path for name, spec in TOOL_SPECS.items()}

TOOL_ALIASES: dict[str, str] = {
    "aircraft": "flights",
    "flight": "flights",
    "live-news": "live_news",
    "country-risk": "country_risk",
    "region-dossier": "region_dossier",
}

FORBIDDEN_ACTIVE_PATHS = {"/api/scanner", "/api/osint/sweep"}


def normalize_tool_name(tool: str) -> str:
    normalized = tool.strip().lower().replace("-", "_")
    return TOOL_ALIASES.get(normalized, normalized)


def tool_catalog() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, spec in sorted(TOOL_SPECS.items()):
        row = asdict(spec)
        row["source_policy"] = asdict(policy_for_tool(name))
        rows.append(row)
    return rows


class OsirisClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        max_response_bytes: int | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.osiris_base_url).rstrip("/")
        self.timeout = timeout or settings.tool_timeout_seconds
        self.max_response_bytes = max_response_bytes or settings.max_evidence_bytes
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "OsirisClient":
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers={"User-Agent": "OSIRIS-Fusion/1.0 read-only research client"},
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def tool_url(self, tool: str) -> str:
        canonical = normalize_tool_name(tool)
        if canonical not in READ_ONLY_TOOLS:
            raise PermissionError(f"Tool not allowed in read-only mode: {tool}")
        path = READ_ONLY_TOOLS[canonical]
        if path in FORBIDDEN_ACTIVE_PATHS:
            raise PermissionError(f"Active OSIRIS route cannot be called autonomously: {path}")
        return self.base_url + path

    async def _get(self, url: str, params: dict[str, Any] | None = None) -> Any:
        if self._client is None:
            raise RuntimeError("OsirisClient must be used as an async context manager")
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = await self._client.get(url, params=params or {})
                response.raise_for_status()
                length = response.headers.get("content-length")
                if length and int(length) > self.max_response_bytes:
                    raise ValueError("OSIRIS response exceeds configured size limit")
                content = response.content
                if len(content) > self.max_response_bytes:
                    raise ValueError("OSIRIS response exceeds configured size limit")
                content_type = response.headers.get("content-type", "")
                if "json" not in content_type.lower() and content.strip()[:1] not in {b"{", b"["}:
                    raise ValueError("OSIRIS endpoint returned non-JSON content")
                return response.json()
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt == 2:
                    raise
                await asyncio.sleep(0.25 * (2**attempt))
        raise RuntimeError(f"OSIRIS request failed: {last_error}")

    async def fetch_tool(self, tool: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        canonical = normalize_tool_name(tool)
        url = self.tool_url(canonical)
        policy = asdict(policy_for_tool(canonical))
        try:
            data = await self._get(url, params)
            record = make_evidence_record(tool=canonical, source_url=url, data=data)
        except Exception as exc:
            record = make_evidence_record(
                tool=canonical,
                source_url=url,
                error=f"{type(exc).__name__}: {exc}",
            )
        record["source_policy"] = policy
        return record

    async def health(self) -> Any:
        return await self._get(self.base_url + "/api/health")

    async def stats(self) -> Any:
        return await self._get(self.base_url + "/api/stats")

    async def passive_contract_probe(self) -> dict[str, Any]:
        health, stats = await asyncio.gather(self.health(), self.stats())
        return {
            "status": "ok",
            "base_url": self.base_url,
            "health": health,
            "stats": stats,
            "registered_tools": sorted(READ_ONLY_TOOLS),
            "forbidden_active_paths": sorted(FORBIDDEN_ACTIVE_PATHS),
        }
