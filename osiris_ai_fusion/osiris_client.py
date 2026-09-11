from __future__ import annotations

import asyncio
from typing import Any

import httpx

from config import get_settings
from provenance import make_evidence_record


READ_ONLY_TOOLS: dict[str, str] = {
    "earthquakes": "/api/earthquakes",
    "fires": "/api/fires",
    "air_quality": "/api/air-quality",
    "conflicts": "/api/conflicts",
    "country_risk": "/api/country-risk",
    "cyber_threats": "/api/cyber-threats",
    "cyber_attacks": "/api/cyber-attacks",
    "crypto": "/api/crypto",
    "cctv": "/api/cctv",
    "aircraft": "/api/aircraft",
}


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
        self._client = httpx.AsyncClient(timeout=self.timeout, follow_redirects=True)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def tool_url(self, tool: str) -> str:
        if tool not in READ_ONLY_TOOLS:
            raise PermissionError(f"Tool not allowed in read-only mode: {tool}")
        return self.base_url + READ_ONLY_TOOLS[tool]

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
        url = self.tool_url(tool)
        try:
            data = await self._get(url, params)
            return make_evidence_record(tool=tool, source_url=url, data=data)
        except Exception as exc:
            return make_evidence_record(tool=tool, source_url=url, error=f"{type(exc).__name__}: {exc}")

    async def health(self) -> Any:
        return await self._get(self.base_url + "/api/health")
