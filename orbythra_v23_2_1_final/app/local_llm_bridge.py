from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="ORBYTHRA Local LLM Bridge", docs_url=None, redoc_url=None)


class GenerateRequest(BaseModel):
    model_id: str = Field(default="", max_length=200)
    prompt: str = Field(min_length=1, max_length=100000)


def _ollama_url() -> str:
    return os.getenv("ORBYTHRA_OLLAMA_URL", "http://ollama:11434").rstrip("/")


def _default_model() -> str:
    return os.getenv("ORBYTHRA_LOCAL_MODEL_ID", "qwen2.5:0.5b").strip() or "qwen2.5:0.5b"


@app.get("/health")
def health() -> dict[str, object]:
    model = _default_model()
    request = urllib.request.Request(
        f"{_ollama_url()}/api/tags",
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            raw = response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise HTTPException(status_code=503, detail="local_llm_unavailable") from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="invalid_ollama_health_response") from exc

    models = parsed.get("models") if isinstance(parsed, dict) else None
    if not isinstance(models, list):
        raise HTTPException(status_code=502, detail="invalid_ollama_health_response")

    available_models = {
        str(item.get("name") or item.get("model") or "").strip()
        for item in models
        if isinstance(item, dict)
    }
    available_models.discard("")
    if model not in available_models:
        raise HTTPException(status_code=503, detail="local_llm_model_not_ready")

    return {
        "status": "ok",
        "provider": "ollama",
        "model": model,
        "model_loaded": True,
        "available_model_count": len(available_models),
        "confidence_calibrated": False,
    }


@app.post("/generate")
def generate(body: GenerateRequest) -> dict[str, Any]:
    model = body.model_id.strip()
    if not model or model == "default":
        model = _default_model()

    payload = json.dumps(
        {
            "model": model,
            "prompt": body.prompt,
            "stream": False,
            "options": {"temperature": 0.2},
        },
        separators=(",", ":"),
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{_ollama_url()}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise HTTPException(status_code=503, detail="local_llm_unavailable") from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="invalid_local_llm_response") from exc

    output = parsed.get("response") if isinstance(parsed, dict) else None
    if not isinstance(output, str) or not output.strip():
        raise HTTPException(status_code=502, detail="invalid_local_llm_output")

    # Ollama does not return a calibrated probability for free-form generations.
    # 0.50 is deliberately conservative and is not presented as a measured model confidence.
    return {
        "output": output.strip(),
        "confidence": 0.50,
        "confidence_calibrated": False,
        "provider": "local_ollama",
        "model_id": model,
        "provider_response_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    }
