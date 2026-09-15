from __future__ import annotations

import json
import re
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
    """Local-first model router with structured-output support.

    Ollama is the default so the product can run privately. A generic
    OpenAI-compatible endpoint can be configured as a fallback without coupling
    the core to a single hosted vendor.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.local_base_url = settings.ollama_base_url
        self.local_model = settings.llm_model
        self.local_think = settings.llm_think
        self.fallback_base_url = settings.fallback_base_url
        self.fallback_api_key = settings.fallback_api_key
        self.fallback_model = settings.fallback_model
        self.timeout = settings.llm_timeout_seconds

    async def _ollama(
        self,
        system: str,
        prompt: str,
        json_schema: dict[str, Any] | None = None,
    ) -> ModelResult:
        payload: dict[str, Any] = {
            "model": self.local_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "options": {"temperature": 0.1},
        }
        if json_schema is not None:
            payload["format"] = json_schema
        if self.local_model.startswith("qwen3"):
            payload["think"] = self.local_think
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
            if not text.strip():
                raise RuntimeError("Fallback model returned an empty response")
            return ModelResult(
                text=text,
                provider="openai-compatible-fallback",
                model=self.fallback_model,
            )

    async def generate(
        self,
        system: str,
        prompt: str,
        json_schema: dict[str, Any] | None = None,
    ) -> ModelResult:
        try:
            return await self._ollama(system, prompt, json_schema=json_schema)
        except Exception:
            if self.fallback_base_url:
                return await self._fallback(system, prompt)
            raise

    async def generate_json(
        self,
        system: str,
        prompt: str,
        json_schema: dict[str, Any],
    ) -> tuple[dict[str, Any], ModelResult]:
        result = await self.generate(system, prompt, json_schema=json_schema)
        text = result.text.strip()
        try:
            return json.loads(text), result
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, flags=re.DOTALL)
            if not match:
                raise RuntimeError("Model did not return a JSON object")
            return json.loads(match.group(0)), result

    async def health(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(self.local_base_url + "/api/tags")
            response.raise_for_status()
            data = response.json()
            available = {item.get("name", "") for item in data.get("models", [])}
            return {
                "status": "ok",
                "provider": "ollama",
                "model": self.local_model,
                "model_available": self.local_model in available or any(
                    item.startswith(self.local_model + ":") for item in available
                ),
            }
