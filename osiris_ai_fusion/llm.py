from __future__ import annotations

import os
from typing import Any

import httpx


class LocalLLM:
    """Minimal Ollama adapter. Keeps the core free/local by default."""

    def __init__(self) -> None:
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        self.model = os.getenv("LLM_MODEL", "qwen2.5:7b")

    async def generate(self, system: str, prompt: str) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(self.base_url + "/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "")
