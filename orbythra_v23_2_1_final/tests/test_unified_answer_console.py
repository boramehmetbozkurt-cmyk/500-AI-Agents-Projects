from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api import app
from app.config import SETTINGS
from app.unified_answer import UnifiedSource
import app.unified_answer as unified


def headers() -> dict[str, str]:
    return {"X-API-Key": SETTINGS.api_keys[0][1], "X-Workspace-ID": "default"}


def _pass_assurance() -> SimpleNamespace:
    return SimpleNamespace(
        status="PASS",
        gates=[],
        claim_verdicts=[],
        output_sha256="a" * 64,
        evidence_manifest_sha256="b" * 64,
    )


def _wire_passing_pipeline(monkeypatch) -> None:
    monkeypatch.setattr(
        unified,
        "SETTINGS",
        SimpleNamespace(release_sha="1" * 40),
    )
    monkeypatch.setattr(
        unified,
        "provider_status",
        lambda: SimpleNamespace(
            google_search_configured=True,
            evidence_provider_configured=False,
            llm_provider_configured=True,
        ),
    )
    monkeypatch.setattr(
        unified,
        "_search",
        lambda query, limit: ([{
            "source_id": "s1",
            "title": "Official source",
            "url": "https://example.com/source",
            "publisher": "example.com",
            "snippet": "Verified fact is supported by the official source.",
            "source_type": "test",
        }], "google"),
    )
    source = UnifiedSource(
        source_id="s1",
        title="Official source",
        url="https://example.com/source",
        publisher="example.com",
        retrieved_at=1_800_000_000,
        snippet="Verified fact is supported by the official source.",
        source_type="test",
        direct_fetch=True,
    )
    monkeypatch.setattr(
        unified,
        "_collect_direct_evidence",
        lambda discovered: ([source], {"s1": "Verified fact is supported by the official source."}, []),
    )
    monkeypatch.setattr(
        unified,
        "_generate_answer",
        lambda **kwargs: ("Verified fact is supported by the official source.", 0.91, "test-model", []),
    )
    monkeypatch.setattr(
        unified,
        "_v1_verification",
        lambda *args, **kwargs: {"disposition": "ANSWER", "evidence_gate_pass_rate": 1.0, "verdicts": []},
    )
    monkeypatch.setattr(unified, "assure_model_output", lambda *args, **kwargs: _pass_assurance())


def test_unified_answer_returns_pass_for_verified_pipeline(monkeypatch) -> None:
    _wire_passing_pipeline(monkeypatch)
    response = TestClient(app).post(
        "/v11/answer",
        json={"query": "What is the verified fact?", "mode": "AUTO"},
        headers=headers(),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "PASS"
    assert data["answer"].startswith("Verified fact")
    assert data["verification"]["passed"] is True
    assert data["verification"]["direct_source_count"] == 1
    assert "/v1/plan" in data["receipt"]["routed_endpoints"]
    assert "/v1/verify" in data["receipt"]["routed_endpoints"]
    assert "/v5.1/model-output/evaluate" in data["receipt"]["routed_endpoints"]


def test_request_id_and_nonce_digest_change_each_run(monkeypatch) -> None:
    _wire_passing_pipeline(monkeypatch)
    client = TestClient(app)
    payload = {"query": "Who is responsible for this verified fact?", "mode": "AUTO"}
    first = client.post("/v11/answer", json=payload, headers=headers()).json()
    second = client.post("/v11/answer", json=payload, headers=headers()).json()
    assert first["receipt"]["request_id"] != second["receipt"]["request_id"]
    assert first["receipt"]["nonce_sha256"] != second["receipt"]["nonce_sha256"]
    assert "nonce" not in first["receipt"]


def test_web_mode_fails_gracefully_without_search_provider(monkeypatch) -> None:
    monkeypatch.setattr(
        unified,
        "provider_status",
        lambda: SimpleNamespace(
            google_search_configured=False,
            evidence_provider_configured=False,
            llm_provider_configured=True,
        ),
    )
    response = TestClient(app).post(
        "/v11/answer",
        json={"query": "What happened today?", "mode": "WEB_RESEARCH"},
        headers=headers(),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ERROR"
    assert data["error_code"] == "search_provider_unavailable"


def test_readiness_exposes_provider_and_release_state(monkeypatch) -> None:
    monkeypatch.setattr(
        unified,
        "provider_status",
        lambda: SimpleNamespace(
            google_search_configured=True,
            evidence_provider_configured=True,
            llm_provider_configured=True,
        ),
    )
    monkeypatch.setattr(unified, "SETTINGS", SimpleNamespace(release_sha="2" * 40))
    response = TestClient(app).get("/v11/answer/readiness", headers=headers())
    assert response.status_code == 200
    data = response.json()
    assert data["unified_answer_console"] is True
    assert data["google_search_configured"] is True
    assert data["llm_provider_configured"] is True
    assert data["release_binding_configured"] is True
    assert data["raw_nonce_exposed"] is False
