from __future__ import annotations

from app.unified_answer import UnifiedAnswerResponse
from app.unified_answer_policy import _apply_console_policy


def _blocked(failed_gates: list[str], *, mode: str = "AI_ANALYSIS") -> UnifiedAnswerResponse:
    return UnifiedAnswerResponse(
        query="Sam Altman is CEO of OpenAI",
        status="BLOCKED",
        answer="Sam Altman is CEO of OpenAI.",
        confidence=0.5,
        sources=[],
        claims=[],
        verification={
            "passed": False,
            "failed_gates": failed_gates,
            "direct_source_count": 0,
        },
        pipeline=[],
        receipt={},
        warnings=[],
        effective_mode=mode,
    )


def test_ai_only_missing_evidence_becomes_review_with_answer_visible() -> None:
    result = _apply_console_policy(
        _blocked([
            "evidence_present",
            "claim_support",
            "evidence_coverage",
            "nli_verifier",
            "direct_source_evidence",
            "v1_evidence_gate",
        ])
    )
    assert result.status == "REVIEW"
    assert result.answer == "Sam Altman is CEO of OpenAI."
    assert result.verification["passed"] is False
    assert result.verification["verified_release"] is False
    assert result.verification["review_reason"] == "external_evidence_unavailable"
    assert "unverified_ai_answer:external_evidence_required_for_verified_pass" in result.warnings


def test_contradiction_failure_remains_blocked() -> None:
    result = _apply_console_policy(_blocked(["evidence_present", "no_contradictions"]))
    assert result.status == "BLOCKED"


def test_low_confidence_failure_remains_blocked() -> None:
    result = _apply_console_policy(_blocked(["confidence", "evidence_present"]))
    assert result.status == "BLOCKED"


def test_web_research_never_downgrades_block_to_review() -> None:
    result = _apply_console_policy(_blocked(["evidence_present"], mode="WEB_RESEARCH"))
    assert result.status == "BLOCKED"


def test_static_general_question_keeps_ai_answer_when_web_evidence_is_only_discovery(monkeypatch) -> None:
    from types import SimpleNamespace
    from fastapi.testclient import TestClient

    import app.unified_answer as unified
    from app.api import app
    from app.config import SETTINGS

    monkeypatch.setattr(unified, "SETTINGS", SimpleNamespace(release_sha="1" * 40))
    monkeypatch.setattr(
        unified,
        "provider_status",
        lambda: SimpleNamespace(
            google_search_configured=True,
            evidence_provider_configured=False,
            keyless_search_configured=False,
            llm_provider_configured=True,
        ),
    )
    monkeypatch.setattr(
        unified,
        "_search",
        lambda query, limit: ([{
            "source_id": "btc-discovery",
            "title": "Bitcoin overview",
            "url": "https://example.com/bitcoin",
            "publisher": "example.com",
            "snippet": "Discovery snippet must not become evidence.",
            "source_type": "google_programmable_search",
        }], "google"),
    )
    discovery = unified.UnifiedSource(
        source_id="btc-discovery",
        title="Bitcoin overview",
        url="https://example.com/bitcoin",
        publisher="example.com",
        retrieved_at=1_800_000_000,
        snippet=None,
        source_type="google_programmable_search",
        direct_fetch=False,
        evidence_status="DISCOVERY_ONLY",
    )
    monkeypatch.setattr(
        unified,
        "_collect_direct_evidence",
        lambda discovered: ([discovery], {}, ["direct_source_fetch_failed:btc-discovery"]),
    )
    monkeypatch.setattr(
        unified,
        "_generate_answer",
        lambda **kwargs: (
            "Bitcoin, merkezi bir otoriteye ihtiyaç duymadan çalışan eşler arası dijital para ağıdır.",
            0.91,
            "test-model",
            [],
        ),
    )
    monkeypatch.setattr(
        unified,
        "_v1_verification",
        lambda *args, **kwargs: {
            "disposition": "ABSTAIN_OR_QUALIFY",
            "evidence_gate_pass_rate": 0.0,
            "verdicts": [],
        },
    )
    evidence_only_gates = [
        SimpleNamespace(name="confidence", passed=True),
        SimpleNamespace(name="evidence_present", passed=False),
        SimpleNamespace(name="claim_support", passed=False),
        SimpleNamespace(name="evidence_coverage", passed=False),
        SimpleNamespace(name="nli_verifier", passed=False),
        SimpleNamespace(name="no_contradictions", passed=True),
        SimpleNamespace(name="evidence_freshness", passed=True),
        SimpleNamespace(name="source_url_shape", passed=True),
        SimpleNamespace(name="release_binding", passed=True),
        SimpleNamespace(name="high_risk_human_approval", passed=True),
    ]
    monkeypatch.setattr(
        unified,
        "assure_model_output",
        lambda *args, **kwargs: SimpleNamespace(
            status="FAIL",
            gates=evidence_only_gates,
            claim_verdicts=[],
            output_sha256="a" * 64,
            evidence_manifest_sha256="b" * 64,
        ),
    )

    client = TestClient(app)
    headers = {"X-API-Key": SETTINGS.api_keys[0][1], "X-Workspace-ID": "default"}
    for query in ("BTC nedir?", "What is Bitcoin?"):
        response = client.post("/v11/answer", json={"query": query, "mode": "AUTO"}, headers=headers)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["status"] == "REVIEW"
        assert data["effective_mode"] == "AI_ANALYSIS"
        assert data["answer"].startswith("Bitcoin")
        assert data["verification"]["answer_released"] is True
        assert data["verification"]["review_reason"] == "external_evidence_unavailable"
        assert data["sources"][0]["evidence_status"] == "DISCOVERY_ONLY"
        assert data["sources"][0]["snippet"] is None


def test_auto_person_profile_lookup_stays_fail_closed_without_direct_evidence(monkeypatch) -> None:
    from types import SimpleNamespace
    from fastapi.testclient import TestClient

    import app.unified_answer as unified
    from app.api import app
    from app.config import SETTINGS

    monkeypatch.setattr(
        unified,
        "provider_status",
        lambda: SimpleNamespace(
            google_search_configured=True,
            evidence_provider_configured=False,
            keyless_search_configured=False,
            llm_provider_configured=True,
        ),
    )
    monkeypatch.setattr(
        unified,
        "_search",
        lambda query, limit: ([{
            "source_id": "person-discovery",
            "title": "Example Person - LinkedIn",
            "url": "https://www.linkedin.com/in/example-person",
            "publisher": "linkedin.com",
            "snippet": "Unverified profile snippet.",
            "source_type": "google_programmable_search",
        }], "google"),
    )
    source = unified.UnifiedSource(
        source_id="person-discovery",
        title="Example Person - LinkedIn",
        url="https://www.linkedin.com/in/example-person",
        publisher="linkedin.com",
        retrieved_at=1_800_000_000,
        snippet=None,
        source_type="google_programmable_search",
        direct_fetch=False,
        evidence_status="DISCOVERY_ONLY",
    )
    monkeypatch.setattr(
        unified,
        "_collect_direct_evidence",
        lambda discovered: ([source], {}, ["direct_source_fetch_failed:person-discovery"]),
    )

    response = TestClient(app).post(
        "/v11/answer",
        json={"query": "Who is Example Person?", "mode": "AUTO"},
        headers={"X-API-Key": SETTINGS.api_keys[0][1], "X-Workspace-ID": "default"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["effective_mode"] == "WEB_RESEARCH"
    assert data["status"] == "BLOCKED"
    assert data["answer"] is None
    assert data["error_code"] == "verified_evidence_unavailable"
    assert data["sources"][0]["evidence_status"] == "DISCOVERY_ONLY"
