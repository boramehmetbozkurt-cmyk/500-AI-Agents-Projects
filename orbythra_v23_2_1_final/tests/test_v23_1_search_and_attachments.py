from __future__ import annotations

import io
import os
import zipfile
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.unified_answer as unified
from app.api import app
from app.attachments import ATTACHMENTS
from app.providers import DuckDuckGoSearchProvider, ProviderStatus


def headers(workspace: str = "default") -> dict[str, str]:
    return {"X-API-Key": "test-secret", "X-Workspace-ID": workspace}


@pytest.fixture(autouse=True)
def _clean_attachments():
    ATTACHMENTS.clear()
    yield
    ATTACHMENTS.clear()


def _no_search_providers(monkeypatch, keyless: bool) -> None:
    monkeypatch.setattr(
        unified,
        "provider_status",
        lambda: SimpleNamespace(
            google_search_configured=False,
            evidence_provider_configured=False,
            llm_provider_configured=False,
            keyless_search_configured=keyless,
        ),
    )


def _docx_bytes(paragraphs: list[str]) -> bytes:
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", xml)
    return buffer.getvalue()


def test_upload_text_file_and_list_is_workspace_scoped() -> None:
    client = TestClient(app)
    response = client.post(
        "/v11/answer/files",
        files={"file": ("notes.md", b"# Project Orion\nThe launch window opens on 14 March 2027.\n", "text/markdown")},
        headers=headers(),
    )
    assert response.status_code == 201, response.text
    meta = response.json()
    assert meta["kind"] == "text"
    assert meta["text_chars"] > 20
    assert "Project Orion" in meta["preview"]
    assert client.get("/v11/answer/files", headers=headers()).json()[0]["attachment_id"] == meta["attachment_id"]
    assert client.get("/v11/answer/files", headers=headers("other-workspace")).json() == []
    assert client.delete(f"/v11/answer/files/{meta['attachment_id']}", headers=headers()).status_code == 204
    assert client.get("/v11/answer/files", headers=headers()).json() == []


def test_upload_docx_and_reject_unsupported_type() -> None:
    client = TestClient(app)
    ok = client.post(
        "/v11/answer/files",
        files={"file": ("report.docx", _docx_bytes(["Quarterly revenue grew 12 percent.", "Churn fell to 3 percent."]), "application/octet-stream")},
        headers=headers(),
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["kind"] == "docx"
    assert "Quarterly revenue" in ok.json()["preview"]
    bad = client.post("/v11/answer/files", files={"file": ("x.exe", b"\x00\x01\x02", "application/octet-stream")}, headers=headers())
    assert bad.status_code == 415


def test_upload_pdf_is_extracted() -> None:
    pypdf = pytest.importorskip("pypdf")
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    client = TestClient(app)
    response = client.post("/v11/answer/files", files={"file": ("blank.pdf", buffer.getvalue(), "application/pdf")}, headers=headers())
    assert response.status_code == 201, response.text
    assert response.json()["kind"] == "pdf"
    assert "pdf_has_no_extractable_text:scanned_or_image_only" in response.json()["warnings"]


def test_agent_answers_from_attachment_without_llm_or_search(monkeypatch) -> None:
    _no_search_providers(monkeypatch, keyless=False)
    client = TestClient(app)
    text = (
        "The ORBYTHRA release train ships every second Tuesday. "
        "The current release owner is Deniz Kaya. "
        "Rollback drills are mandatory before each production deploy."
    )
    meta = client.post("/v11/answer/files", files={"file": ("runbook.txt", text.encode(), "text/plain")}, headers=headers()).json()
    response = client.post(
        "/v11/answer",
        json={"query": "Who is the current release owner according to the attached file?", "mode": "AUTO", "attachment_ids": [meta["attachment_id"]]},
        headers=headers(),
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] in {"PASS", "REVIEW"}
    assert "Deniz Kaya" in (data["answer"] or "")
    steps = {step["step"]: step for step in data["pipeline"]}
    assert "file_context" in steps["tool_selection"]["detail"]
    assert "web_search" not in steps["tool_selection"]["detail"]
    assert steps["reading_attachments"]["status"] == "PASS"
    assert data["sources"][0]["source_type"] == "attachment"
    assert data["receipt"]["selected_tools"] == ["file_context"]
    assert data["verification"]["direct_source_count"] == 1


def test_unknown_attachment_id_is_reported_not_fatal(monkeypatch) -> None:
    _no_search_providers(monkeypatch, keyless=False)
    response = TestClient(app).post(
        "/v11/answer",
        json={"query": "Summarize the attached document please", "mode": "AI_ANALYSIS", "attachment_ids": ["file-missing"]},
        headers=headers(),
    )
    assert response.status_code == 200
    assert any(w.startswith("attachments_not_found_or_expired") for w in response.json()["warnings"])


def test_keyless_search_is_selected_when_no_keyed_provider(monkeypatch) -> None:
    _no_search_providers(monkeypatch, keyless=True)
    calls: dict[str, str] = {}

    class _FakeKeyless:
        def search(self, query: str, *, limit: int = 5, timeout: float = 12.0):
            calls["query"] = query
            return [{
                "source_id": "bing-1",
                "title": "Example fact page",
                "url": "https://example.com/fact",
                "publisher": "example.com",
                "snippet": "Ankara is the capital of Turkey.",
                "source_type": "bing_html",
            }]

    monkeypatch.setattr(unified, "keyless_search_provider", lambda: _FakeKeyless())
    monkeypatch.setattr(
        unified,
        "fetch_public_source",
        lambda src, timeout, max_bytes: (SimpleNamespace(published_at=None), "Ankara is the capital of Turkey. It became the capital in 1923."),
    )
    response = TestClient(app).post("/v11/answer", json={"query": "What is the capital of Turkey?", "mode": "AUTO"}, headers=headers())
    assert response.status_code == 200, response.text
    data = response.json()
    assert calls["query"] == "What is the capital of Turkey?"
    assert data["effective_mode"] == "WEB_RESEARCH"
    steps = {step["step"]: step for step in data["pipeline"]}
    assert "provider=keyless_web_search" in steps["searching_sources"]["detail"]
    assert data["sources"][0]["direct_fetch"] is True
    assert "Ankara" in (data["answer"] or "")


def test_provider_status_exposes_keyless_flag(monkeypatch) -> None:
    monkeypatch.setenv("ORBYTHRA_KEYLESS_SEARCH", "false")
    from app import providers

    assert providers.status().keyless_search_configured is False
    monkeypatch.setenv("ORBYTHRA_KEYLESS_SEARCH", "true")
    assert providers.status().keyless_search_configured is True
    assert ProviderStatus(False, False, keyless_search_configured=True).web_search_configured is True


def test_bing_redirect_urls_are_decoded() -> None:
    wrapped = "https://www.bing.com/ck/a?!&&p=abc&u=a1aHR0cHM6Ly9vcGVuYWkuY29tLw&ntb=1"
    assert DuckDuckGoSearchProvider._resolve_bing_url(wrapped) == "https://openai.com/"
    ddg = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage&rut=1"
    assert DuckDuckGoSearchProvider._resolve_redirect(ddg) == "https://example.com/page"


@pytest.mark.skipif(os.getenv("ORBYTHRA_LIVE_SEARCH_TEST") != "1", reason="live network smoke test; set ORBYTHRA_LIVE_SEARCH_TEST=1")
def test_live_keyless_search_smoke() -> None:
    results = DuckDuckGoSearchProvider().search("Python programming language", limit=3)
    assert results and results[0]["url"].startswith("http")


def test_discovery_snippet_is_never_used_as_evidence_or_answer(monkeypatch) -> None:
    """Regression: a Google/LinkedIn-style snippet cannot leak into a verified answer when page fetch fails."""
    monkeypatch.setattr(
        unified,
        "provider_status",
        lambda: SimpleNamespace(
            google_search_configured=True,
            evidence_provider_configured=False,
            llm_provider_configured=True,
            keyless_search_configured=False,
        ),
    )

    class _Search:
        def search(self, query: str, *, limit: int = 5, timeout: float = 15.0):
            return [{
                "source_id": "google-1",
                "title": "Example Person - LinkedIn",
                "url": "https://www.linkedin.com/in/example-person",
                "publisher": "linkedin.com",
                "snippet": "Example Person is Secret Title at Secret Company.",
                "source_type": "google_programmable_search",
            }]

    monkeypatch.setattr(unified, "google_search_provider", lambda: _Search())
    monkeypatch.setattr(unified, "fetch_public_source", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("blocked")))

    class _MustNotRun:
        def __init__(self, *args, **kwargs):
            raise AssertionError("LLM must not run without direct web evidence")

    monkeypatch.setattr(unified, "GovernedHttpModelAdapter", _MustNotRun)
    response = TestClient(app).post(
        "/v11/answer",
        json={"query": "Who is Example Person?", "mode": "WEB_RESEARCH"},
        headers=headers(),
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "BLOCKED"
    assert data["answer"] is None
    assert data["claims"] == []
    assert data["error_code"] == "verified_evidence_unavailable"
    assert data["sources"][0]["direct_fetch"] is False
    assert data["sources"][0]["evidence_status"] == "DISCOVERY_ONLY"
    assert data["sources"][0]["snippet"] is None
    assert data["verification"]["direct_source_count"] == 0


def test_search_provider_full_text_is_not_trusted_without_direct_fetch(monkeypatch) -> None:
    discovered = [{
        "source_id": "provider-1",
        "title": "Untrusted provider payload",
        "url": "https://example.com/private-profile",
        "publisher": "example.com",
        "snippet": "snippet secret",
        "full_text": "provider supplied secret profile data",
        "source_type": "evidence_provider",
    }]
    monkeypatch.setattr(unified, "fetch_public_source", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("blocked")))
    sources, texts, warnings = unified._collect_direct_evidence(discovered)
    assert texts == {}
    assert sources[0].direct_fetch is False
    assert sources[0].evidence_status == "DISCOVERY_ONLY"
    assert sources[0].snippet is None
    assert warnings == ["direct_source_fetch_failed:provider-1"]
