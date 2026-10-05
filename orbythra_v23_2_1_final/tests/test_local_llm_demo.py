from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

import app.local_llm_bridge as bridge


class _FakeResponse:
    def __init__(self, payload: dict | None = None):
        self.payload = payload or {"response": "Local model answer.", "done": True}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_local_llm_bridge_maps_ollama_to_orbythra_provider_contract(monkeypatch) -> None:
    monkeypatch.setenv("ORBYTHRA_LOCAL_MODEL_ID", "qwen2.5:0.5b")
    monkeypatch.setattr(bridge.urllib.request, "urlopen", lambda request, timeout=0: _FakeResponse())
    response = TestClient(bridge.app).post(
        "/generate",
        json={"model_id": "default", "prompt": "Explain the system."},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["output"] == "Local model answer."
    assert data["provider"] == "local_ollama"
    assert data["model_id"] == "qwen2.5:0.5b"
    assert data["confidence"] == 0.5
    assert data["confidence_calibrated"] is False
    assert len(data["provider_response_sha256"]) == 64


def test_demo_compose_has_zero_config_local_llm_fallback() -> None:
    text = Path("docker-compose.demo.yml").read_text(encoding="utf-8")
    assert "ollama:" in text
    assert "ollama-init:" in text
    assert "local-llm:" in text
    assert "qwen2.5:0.5b" in text
    assert "ORBYTHRA_LLM_PROVIDER_URL: ${ORBYTHRA_LLM_PROVIDER_URL:-http://local-llm:9000}" in text
    assert "condition: service_completed_successfully" in text


def test_external_llm_can_override_local_demo_fallback() -> None:
    text = Path("docker-compose.demo.yml").read_text(encoding="utf-8")
    assert "${ORBYTHRA_LLM_PROVIDER_URL:-http://local-llm:9000}" in text
    assert "${ORBYTHRA_LLM_PROVIDER_TOKEN:-}" in text


def test_local_llm_health_requires_ollama_and_loaded_model(monkeypatch) -> None:
    monkeypatch.setenv("ORBYTHRA_LOCAL_MODEL_ID", "qwen2.5:0.5b")
    monkeypatch.setattr(
        bridge.urllib.request,
        "urlopen",
        lambda request, timeout=0: _FakeResponse({"models": [{"name": "qwen2.5:0.5b"}]}),
    )
    response = TestClient(bridge.app).get("/health")
    assert response.status_code == 200
    assert response.json()["model_loaded"] is True
    assert response.json()["available_model_count"] == 1


def test_local_llm_health_fails_when_ollama_is_unavailable(monkeypatch) -> None:
    def unavailable(request, timeout=0):
        raise bridge.urllib.error.URLError("offline")

    monkeypatch.setattr(bridge.urllib.request, "urlopen", unavailable)
    response = TestClient(bridge.app).get("/health")
    assert response.status_code == 503
    assert response.json()["detail"] == "local_llm_unavailable"


def test_local_llm_health_fails_until_configured_model_is_loaded(monkeypatch) -> None:
    monkeypatch.setenv("ORBYTHRA_LOCAL_MODEL_ID", "qwen2.5:0.5b")
    monkeypatch.setattr(
        bridge.urllib.request,
        "urlopen",
        lambda request, timeout=0: _FakeResponse({"models": [{"name": "other:latest"}]}),
    )
    response = TestClient(bridge.app).get("/health")
    assert response.status_code == 503
    assert response.json()["detail"] == "local_llm_model_not_ready"
