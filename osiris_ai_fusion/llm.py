from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from config import get_settings


@dataclass(frozen=True)
class ModelResult:
    text: str
    provider: str
    model: str


class ModelRouter:
    """Local-first model router with an optional OpenAI-compatible fallback."""

    def __init__(self) -> None:
        settings = get_settings()
        self.local_base_url = settings.ollama_base_url
        self.local_model = settings.llm_model
        self.fallback_base_url = settings.fallback_base_url
        self.fallback_api_key = settings.fallback_api_key
        self.fallback_model = settings.fallback_model
        self.timeout = settings.llm_timeout_seconds

    async def _ollama(self, system: str, prompt: str) -> ModelResult:
        payload: dict[str, Any] = {
            "model": self.local_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "options": {"temperature": 0.1},
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(self.local_base_url + "/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            text = data.get("message", {}).get("content", "")
            if not text.strip():
                raise RuntimeError("Local model returned an empty response")
            return ModelResult(text=text, provider="ollama", model=self.local_model)

    async def _fallback(self, system: str, prompt: str) -> ModelResult:
        if not (self.fallback_base_url and self.fallback_api_key and self.fallback_model):
            raise RuntimeError("No fallback model is configured")
        headers = {"Authorization": f"Bearer {self.fallback_api_key}"}
        payload = {
            "model": self.fallback_model,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.fallback_base_url + "/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            text = data["choices"][0]["message"]["content"]
            return ModelResult(text=text, provider="openai-compatible-fallback", model=self.fallback_model)

    async def generate(self, system: str, prompt: str) -> ModelResult:
        try:
            return await self._ollama(system, prompt)
        except Exception:
            if self.fallback_base_url:
                return await self._fallback(system, prompt)
            raise

    async def health(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(self.local_base_url + "/api/tags")
            response.raise_for_status()
            return {"status": "ok", "provider": "ollama", "model": self.local_model}
