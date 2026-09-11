from __future__ import annotations

import asyncio
from typing import Any

import httpx

from config import get_settings
from provenance import make_evidence_record

# Canonical passive/read-only OSIRIS feeds verified against the public API docs.
# Active traffic-producing routes such as /api/scanner and /api/osint/sweep are
# intentionally excluded from the autonomous registry.
READ_ONLY_TOOLS: dict[str, str] = {
    "flights": "/api/flights",
    "satellites": "/api/satellites",
    "space_weather": "/api/space-weather",
    "earthquakes": "/api/earthquakes",
    "fires": "/api/fires",
    "weather": "/api/weather",
    "air_quality": "/api/air-quality",
    "radar": "/api/radar",
    "conflicts": "/api/conflicts",
    "frontlines": "/api/frontlines",
    "gdelt": "/api/gdelt",
    "country_risk": "/api/country-risk",
    "news": "/api/news",
    "markets": "/api/markets",
    "crypto": "/api/crypto",
    "cctv": "/api/cctv",
    "infrastructure": "/api/infrastructure",
    "maritime": "/api/maritime",
    "cyber_threats": "/api/cyber-threats",
    "cyber_attacks": "/api/cyber-attacks",
    "malware": "/api/malware",
}

TOOL_ALIASES: dict[str, str] = {
    "aircraft": "flights",
    "flight": "flights",
}

FORBIDDEN_ACTIVE_PATHS = {
    "/api/scanner",
    "/api/osint/sweep",
}


def normalize_tool_name(tool: str) -> str:
    normalized = tool.strip().lower().replace("-", "_")
    return TOOL_ALIASES.get(normalized, normalized)


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

    async def __aenter__(self) -> OsirisClient:
        self._client = httpx.AsyncClient(timeout=self.timeout, follow_redirects=True)
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
        try:
            data = await self._get(url, params)
            return make_evidence_record(tool=canonical, source_url=url, data=data)
        except Exception as exc:
            return make_evidence_record(
                tool=canonical,
                source_url=url,
                error=f"{type(exc).__name__}: {exc}",
            )

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
        }
