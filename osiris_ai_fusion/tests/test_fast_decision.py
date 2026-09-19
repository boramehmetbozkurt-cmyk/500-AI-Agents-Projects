from __future__ import annotations

import httpx
import pytest

import fast_decision
from config import get_settings
from fast_decision import FastDecisionClient, contains_secret_like, deterministic_decision


def test_deterministic_fallback_classifies_research_and_code() -> None:
    result = deterministic_decision(
        "Güncel kaynakları araştır ve koddaki bug'ı düzelt",
        ["provider_federation"],
    )
    assert result.action == "allow"
    assert result.needs_research is True
    assert result.needs_code_agent is True
    assert result.selected_tools == ["provider_federation"]


@pytest.mark.parametrize(
    "query",
    [
        "api_key=super-secret-value-12345",
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz",
        "private key: 0x" + "ab" * 32,
        "token=eyJabcdefgh.ijklmnop.qrstuvwxyz",
        "seed phrase: abandon ability able about above absent absorb abstract absurd abuse access accident",
    ],
)
def test_secret_like_input_is_detected(query: str) -> None:
    assert contains_secret_like(query) is True


async def test_secret_like_input_never_calls_remote(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAST_DECISION_ENABLED", "true")
    monkeypatch.setenv("FAST_DECISION_BASE_URL", "https://decision.example")
    get_settings.cache_clear()

    def forbidden_client(*args, **kwargs):
        raise AssertionError("remote client must not be created for secret-like input")

    monkeypatch.setattr(fast_decision.httpx, "AsyncClient", forbidden_client)
    result = await FastDecisionClient().decide(
        "password=hunter2-super-secret",
        ["direct_reasoning"],
        {},
    )
    assert result.used_remote is False
    assert result.fallback_reason == "secret-like-input"
    assert result.decision.action == "escalate"
    get_settings.cache_clear()


async def test_remote_decision_cannot_invent_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAST_DECISION_ENABLED", "true")
    monkeypatch.setenv("FAST_DECISION_BASE_URL", "https://decision.example")
    get_settings.cache_clear()

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "action": "allow",
                "confidence": 0.99,
                "risk_score": 0.01,
                "needs_reasoning": False,
                "needs_research": True,
                "needs_code_agent": False,
                "selected_tools": ["active_scanner"],
                "reason": "bad route",
            },
        )

    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(fast_decision.httpx, "AsyncClient", client_factory)
    result = await FastDecisionClient().decide(
        "research this",
        ["provider_federation"],
        {},
    )
    assert result.used_remote is False
    assert result.fallback_reason == "ValueError"
    assert result.decision.action == "escalate"
    assert result.decision.selected_tools == ["provider_federation"]
    get_settings.cache_clear()


async def test_remote_deny_is_typed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAST_DECISION_ENABLED", "true")
    monkeypatch.setenv("FAST_DECISION_BASE_URL", "https://decision.example")
    get_settings.cache_clear()

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "decision": {
                    "action": "deny",
                    "confidence": 0.95,
                    "risk_score": 0.9,
                    "needs_reasoning": False,
                    "needs_research": False,
                    "needs_code_agent": False,
                    "selected_tools": [],
                    "reason": "policy",
                }
            },
        )

    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(fast_decision.httpx, "AsyncClient", client_factory)
    result = await FastDecisionClient().decide("test", ["direct_reasoning"], {})
    assert result.used_remote is True
    assert result.decision.action == "deny"
    get_settings.cache_clear()
