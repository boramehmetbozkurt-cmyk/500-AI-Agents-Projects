from __future__ import annotations

import json
from pathlib import Path

from app.providers import GoogleSearchProvider, SerpApiSearchProvider
import app.providers as providers


def test_default_frontend_is_unified_answer_console() -> None:
    source = Path("client/src/main.jsx").read_text(encoding="utf-8")
    # V23.1 Turkish chat UI: default view is the chat/answer console, API explorer is preserved under Advanced.
    assert 'useState("chat")' in source
    assert "ORBYTHRA'ya bir soru sorun" in source
    assert 'request("/v11/answer"' in source
    assert 'downloadFile("/v11/answer/export/xlsx"' in source
    assert "Excel indir" in source
    assert "Gelişmiş / API Konsolu" in source
    assert "function ApiExplorer" in source
    assert "Doğrulama ve Kanıt" in source
    assert "Release SHA" not in source
    assert "Configuration SHA-256" not in source
    assert "model-output-001" not in source
    assert "0123456789abcdef" not in source


def test_demo_passes_provider_secrets_only_to_backend() -> None:
    compose = Path("docker-compose.demo.yml").read_text(encoding="utf-8")
    assert "SERPAPI_API_KEY: ${SERPAPI_API_KEY:-}" in compose
    assert "SERPAPI_KEY: ${SERPAPI_KEY:-}" in compose
    assert "GOOGLE_SEARCH_API_KEY: ${GOOGLE_SEARCH_API_KEY:-}" in compose
    assert "GOOGLE_SEARCH_ENGINE_ID: ${GOOGLE_SEARCH_ENGINE_ID:-}" in compose
    assert "ORBYTHRA_LLM_PROVIDER_URL: ${ORBYTHRA_LLM_PROVIDER_URL:-http://local-llm:9000}" in compose
    assert "ORBYTHRA_RELEASE_SHA:" in compose
    dockerfile = Path("client/Dockerfile").read_text(encoding="utf-8")
    assert "SERPAPI_API_KEY" not in dockerfile
    assert "SERPAPI_KEY" not in dockerfile
    assert "GOOGLE_SEARCH_API_KEY" not in dockerfile
    assert "GOOGLE_SEARCH_ENGINE_ID" not in dockerfile
    assert "ORBYTHRA_LLM_PROVIDER_TOKEN" not in dockerfile
    assert "ORBYTHRA_LLM_PROVIDER_URL" not in dockerfile
    assert "ORBYTHRA_OLLAMA_URL" not in dockerfile


def test_production_compose_does_not_inject_demo_api_key() -> None:
    production = Path("docker-compose.production.yml").read_text(encoding="utf-8")
    assert "SERPAPI_API_KEY: ${SERPAPI_API_KEY:-}" in production
    assert "SERPAPI_KEY: ${SERPAPI_KEY:-}" in production
    assert "VITE_DEMO_API_KEY" not in production
    assert "orbythra-demo-local-key-change-before-sharing" not in production


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_google_search_results_are_normalized(monkeypatch) -> None:
    payload = {
        "items": [
            {
                "title": "Official Example",
                "link": "https://example.com/fact",
                "displayLink": "example.com",
                "snippet": "A source-backed fact.",
            }
        ]
    }
    monkeypatch.setattr(providers.urllib.request, "urlopen", lambda *args, **kwargs: _FakeResponse(payload))
    result = GoogleSearchProvider("secret", "engine").search("example fact", limit=5)
    assert result == [
        {
            "source_id": "google-1",
            "title": "Official Example",
            "url": "https://example.com/fact",
            "publisher": "example.com",
            "snippet": "A source-backed fact.",
            "source_type": "google_programmable_search",
        }
    ]


def test_serpapi_google_results_are_normalized(monkeypatch) -> None:
    payload = {
        "search_metadata": {"status": "Success"},
        "organic_results": [
            {
                "position": 1,
                "title": "OpenAI",
                "link": "https://openai.com/",
                "source": "OpenAI",
                "snippet": "Official OpenAI website.",
                "date": "Sep 30, 2026",
            }
        ],
    }
    captured: dict[str, str] = {}

    def _urlopen(request, *args, **kwargs):
        captured["url"] = request.full_url
        return _FakeResponse(payload)

    monkeypatch.setattr(providers.urllib.request, "urlopen", _urlopen)
    result = SerpApiSearchProvider("serp-secret").search("OpenAI CEO", limit=5)
    assert "engine=google" in captured["url"]
    assert "api_key=serp-secret" in captured["url"]
    assert result == [
        {
            "source_id": "serpapi-google-1",
            "title": "OpenAI",
            "url": "https://openai.com/",
            "publisher": "OpenAI",
            "snippet": "Official OpenAI website.",
            "published_at": "Sep 30, 2026",
            "source_type": "serpapi_google",
        }
    ]


def test_serpapi_is_preferred_google_provider(monkeypatch) -> None:
    monkeypatch.setenv("SERPAPI_API_KEY", "serp-secret")
    monkeypatch.setenv("GOOGLE_SEARCH_API_KEY", "google-secret")
    monkeypatch.setenv("GOOGLE_SEARCH_ENGINE_ID", "google-engine")
    selected = providers.google_search_provider()
    assert isinstance(selected, SerpApiSearchProvider)
    state = providers.status()
    assert state.serpapi_search_configured is True
    assert state.google_search_configured is True


def test_google_programmable_search_remains_fallback(monkeypatch) -> None:
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    monkeypatch.delenv("SERPAPI_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_SEARCH_API_KEY", "google-secret")
    monkeypatch.setenv("GOOGLE_SEARCH_ENGINE_ID", "google-engine")
    assert isinstance(providers.google_search_provider(), GoogleSearchProvider)


def test_multilingual_ui_contract() -> None:
    source = Path("client/src/main.jsx").read_text(encoding="utf-8")
    i18n = Path("client/src/ui_i18n.js").read_text(encoding="utf-8")
    assert "installUiTranslation" in source
    assert "langselect" in source
    for code in ("en", "tr", "de", "fr", "es", "it", "ar"):
        assert f"['{code}'" in i18n
    assert "window.location.reload()" in i18n
    assert "document.documentElement.dir=lang==='ar'?'rtl':'ltr'" in i18n