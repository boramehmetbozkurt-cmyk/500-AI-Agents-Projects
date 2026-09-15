from __future__ import annotations

import asyncio
import os
from dataclasses import asdict, dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class ResearchEngineSpec:
    engine_id: str
    provider: str
    endpoint: str
    api_key_env: str
    model_env: str
    default_model: str
    docs_url: str


def _enabled() -> bool:
    return os.getenv("ORBYTHRA_AI_RESEARCH_ENABLED", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


ENGINES: tuple[ResearchEngineSpec, ...] = (
    ResearchEngineSpec(
        engine_id="google_gemini_search",
        provider="google_gemini",
        endpoint="https://generativelanguage.googleapis.com/v1beta/interactions",
        api_key_env="GEMINI_API_KEY",
        model_env="ORBYTHRA_GEMINI_RESEARCH_MODEL",
        default_model="gemini-3.6-flash",
        docs_url="https://ai.google.dev/gemini-api/docs/google-search",
    ),
    ResearchEngineSpec(
        engine_id="openai_web_search",
        provider="openai",
        endpoint="https://api.openai.com/v1/responses",
        api_key_env="OPENAI_API_KEY",
        model_env="ORBYTHRA_OPENAI_RESEARCH_MODEL",
        default_model="gpt-5.6-terra",
        docs_url="https://developers.openai.com/api/docs/guides/tools-web-search",
    ),
    ResearchEngineSpec(
        engine_id="anthropic_web_search",
        provider="anthropic",
        endpoint="https://api.anthropic.com/v1/messages",
        api_key_env="ANTHROPIC_API_KEY",
        model_env="ORBYTHRA_ANTHROPIC_RESEARCH_MODEL",
        default_model="claude-sonnet-5",
        docs_url="https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool",
    ),
)


def _model(spec: ResearchEngineSpec) -> str:
    return os.getenv(spec.model_env, spec.default_model).strip() or spec.default_model


def engine_ready(spec: ResearchEngineSpec) -> bool:
    return _enabled() and bool(os.getenv(spec.api_key_env, "").strip())


def research_engine_catalog() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in ENGINES:
        row = asdict(spec)
        row["model"] = _model(spec)
        row["ready"] = engine_ready(spec)
        row["missing_configuration"] = (
            [] if row["ready"] else [spec.api_key_env]
        )
        rows.append(row)
    return rows


def _prompt(query: str) -> str:
    return (
        "You are one research sensor inside ORBYTHRA. Research the user's query on the "
        "public web. Prefer primary, official and recent sources when relevant. Answer in "
        "the same language as the user. Distinguish confirmed facts from uncertainty. "
        "Do not invent facts or citations. Return a concise research answer with source "
        "citations. Query:\n\n" + query
    )


def _text_from_openai(payload: dict[str, Any]) -> str:
    chunks: list[str] = []
    for item in payload.get("output", []) if isinstance(payload.get("output"), list) else []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for block in item.get("content", []) if isinstance(item.get("content"), list) else []:
            if isinstance(block, dict) and block.get("type") in {"output_text", "text"}:
                text = block.get("text")
                if isinstance(text, str) and text.strip():
                    chunks.append(text.strip())
    value = payload.get("output_text")
    if isinstance(value, str) and value.strip():
        chunks.append(value.strip())
    return "\n".join(dict.fromkeys(chunks))


def _text_from_anthropic(payload: dict[str, Any]) -> str:
    chunks: list[str] = []
    for block in payload.get("content", []) if isinstance(payload.get("content"), list) else []:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str) and text.strip():
                chunks.append(text.strip())
    return "\n".join(chunks)


def _walk_urls(value: Any, out: list[dict[str, str]]) -> None:
    if isinstance(value, dict):
        url = value.get("url") or value.get("uri")
        if isinstance(url, str) and url.startswith(("https://", "http://")):
            title = value.get("title")
            row = {"url": url, "title": str(title or url)}
            if row not in out:
                out.append(row)
        for nested in value.values():
            _walk_urls(nested, out)
    elif isinstance(value, list):
        for item in value:
            _walk_urls(item, out)


def _find_strings(value: Any, keys: set[str], out: list[str]) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in keys and isinstance(nested, str) and nested.strip():
                out.append(nested.strip())
            else:
                _find_strings(nested, keys, out)
    elif isinstance(value, list):
        for item in value:
            _find_strings(item, keys, out)


def _text_from_google(payload: dict[str, Any]) -> str:
    chunks: list[str] = []
    _find_strings(payload, {"output_text", "text"}, chunks)
    cleaned: list[str] = []
    for text in chunks:
        if text not in cleaned and len(text) >= 12:
            cleaned.append(text)
    return "\n".join(cleaned[:8])


async def _request_google(
    spec: ResearchEngineSpec, query: str, timeout: float, max_response_bytes: int
) -> dict[str, Any]:
    key = os.getenv(spec.api_key_env, "").strip()
    payload = {
        "model": _model(spec),
        "input": _prompt(query),
        "tools": [{"type": "google_search"}],
    }
    headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
    return await _post(spec, payload, headers, timeout, max_response_bytes, _text_from_google)


async def _request_openai(
    spec: ResearchEngineSpec, query: str, timeout: float, max_response_bytes: int
) -> dict[str, Any]:
    key = os.getenv(spec.api_key_env, "").strip()
    payload = {
        "model": _model(spec),
        "input": _prompt(query),
        "tools": [{"type": "web_search"}],
        "include": ["web_search_call.results"],
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    return await _post(spec, payload, headers, timeout, max_response_bytes, _text_from_openai)


async def _request_anthropic(
    spec: ResearchEngineSpec, query: str, timeout: float, max_response_bytes: int
) -> dict[str, Any]:
    key = os.getenv(spec.api_key_env, "").strip()
    payload = {
        "model": _model(spec),
        "max_tokens": 2048,
        "messages": [{"role": "user", "content": _prompt(query)}],
        "tools": [
            {
                "type": "web_search_20260318",
                "name": "web_search",
                "max_uses": 5,
                "allowed_callers": ["direct"],
            }
        ],
    }
    headers = {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    return await _post(spec, payload, headers, timeout, max_response_bytes, _text_from_anthropic)


async def _post(
    spec: ResearchEngineSpec,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: float,
    max_response_bytes: int,
    text_parser,
) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            response = await client.post(spec.endpoint, json=payload, headers=headers)
            response.raise_for_status()
            if len(response.content) > max_response_bytes:
                raise ValueError("AI research response exceeds configured evidence limit")
            data = response.json()
        citations: list[dict[str, str]] = []
        _walk_urls(data, citations)
        return {
            "ok": True,
            "provider_id": spec.engine_id,
            "provider": spec.provider,
            "model": _model(spec),
            "domains": ["ai_research", "web", "global"],
            "freshness": "fresh",
            "source_url": spec.endpoint,
            "answer": text_parser(data),
            "citations": citations[:40],
            "payload": data,
        }
    except Exception as exc:
        return {
            "ok": False,
            "provider_id": spec.engine_id,
            "provider": spec.provider,
            "model": _model(spec),
            "domains": ["ai_research", "web", "global"],
            "source_url": spec.endpoint,
            "error": f"{type(exc).__name__}: {exc}",
        }


async def _run_engine(
    spec: ResearchEngineSpec,
    query: str,
    timeout: float,
    max_response_bytes: int,
) -> dict[str, Any]:
    if spec.provider == "google_gemini":
        return await _request_google(spec, query, timeout, max_response_bytes)
    if spec.provider == "openai":
        return await _request_openai(spec, query, timeout, max_response_bytes)
    if spec.provider == "anthropic":
        return await _request_anthropic(spec, query, timeout, max_response_bytes)
    raise RuntimeError(f"Unsupported research engine: {spec.provider}")


async def fetch_ai_research_council(
    query: str,
    *,
    timeout: float,
    max_response_bytes: int,
) -> dict[str, Any]:
    ready = [spec for spec in ENGINES if engine_ready(spec)]
    try:
        limit = int(os.getenv("ORBYTHRA_AI_RESEARCH_MAX_ENGINES", "3"))
    except ValueError:
        limit = 3
    ready = ready[: max(1, min(3, limit))]
    if not ready:
        return {
            "status": "not_configured",
            "engines_used": [],
            "results": [],
            "missing_configuration": [
                spec.api_key_env for spec in ENGINES if not engine_ready(spec)
            ],
        }
    results = await asyncio.gather(
        *(
            _run_engine(spec, query, timeout, max_response_bytes)
            for spec in ready
        )
    )
    return {
        "status": "ok" if any(item.get("ok") for item in results) else "engine_failure",
        "engines_used": [spec.engine_id for spec in ready],
        "results": results,
    }
