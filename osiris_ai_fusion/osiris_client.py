from __future__ import annotations

import os
from typing import Any

import httpx


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
    def __init__(self, base_url: str | None = None, timeout: float = 20.0) -> None:
        self.base_url = (base_url or os.getenv("OSIRIS_BASE_URL") or "https://osirisai.live").rstrip("/")
        self.timeout = timeout

    async def fetch_tool(self, tool: str, params: dict[str, Any] | None = None) -> Any:
        if tool not in READ_ONLY_TOOLS:
            raise PermissionError(f"Tool not allowed in read-only mode: {tool}")
        url = self.base_url + READ_ONLY_TOOLS[tool]
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await client.get(url, params=params or {})
            response.raise_for_status()
            return response.json()

    async def health(self) -> Any:
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await client.get(self.base_url + "/api/health")
            response.raise_for_status()
            return response.json()
