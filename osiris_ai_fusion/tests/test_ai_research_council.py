import pytest

import ai_research_council as council
import providers


def _clear_keys(monkeypatch):
    for name in ("GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ORBYTHRA_AI_RESEARCH_ENABLED", "true")


def test_research_council_is_optional_and_fail_open(monkeypatch):
    _clear_keys(monkeypatch)
    rows = {row["engine_id"]: row for row in council.research_engine_catalog()}
    assert rows["google_gemini_search"]["ready"] is False
    assert rows["openai_web_search"]["ready"] is False
    assert rows["anthropic_web_search"]["ready"] is False


@pytest.mark.asyncio
async def test_research_council_without_keys_does_not_break_deep_search(monkeypatch):
    _clear_keys(monkeypatch)
    result = await council.fetch_ai_research_council(
        "NVIDIA latest AI developments",
        timeout=1.0,
        max_response_bytes=100_000,
    )
    assert result["status"] == "not_configured"
    assert result["engines_used"] == []
    assert set(result["missing_configuration"]) == {
        "GEMINI_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    }


def test_keys_make_engines_ready(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "test-google")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic")
    rows = {row["engine_id"]: row for row in council.research_engine_catalog()}
    assert all(row["ready"] for row in rows.values())


@pytest.mark.asyncio
async def test_provider_federation_merges_ai_council_results(monkeypatch):
    async def fake_fetch_one(spec, *, query, scope, timeout, max_response_bytes):
        return {
            "ok": True,
            "provider_id": spec.provider_id,
            "provider": spec.provider,
            "source_url": "https://example.invalid",
        }

    async def fake_council(query, *, timeout, max_response_bytes):
        return {
            "status": "ok",
            "engines_used": ["google_gemini_search", "openai_web_search"],
            "results": [
                {
                    "ok": True,
                    "provider_id": "google_gemini_search",
                    "provider": "google_gemini",
                    "source_url": "https://generativelanguage.googleapis.com",
                    "answer": "grounded answer",
                    "citations": [{"url": "https://example.com", "title": "Example"}],
                }
            ],
        }

    monkeypatch.setattr(providers, "_fetch_one", fake_fetch_one)
    monkeypatch.setattr(providers, "fetch_ai_research_council", fake_council)
    result = await providers.fetch_federated(
        "NVIDIA",
        {},
        timeout=1.0,
        max_response_bytes=100_000,
    )
    assert result["status"] == "ok"
    assert "google_gemini_search" in result["ai_engines_used"]
    assert any(item.get("provider") == "google_gemini" for item in result["results"])
