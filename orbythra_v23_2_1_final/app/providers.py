from __future__ import annotations

import base64
import binascii
import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any

from app.config import SETTINGS


@dataclass(frozen=True)
class ProviderStatus:
    evidence_provider_configured: bool
    llm_provider_configured: bool
    google_search_configured: bool = False
    serpapi_search_configured: bool = False
    # Keyless DuckDuckGo HTML discovery. Enabled by default; disable with
    # ORBYTHRA_KEYLESS_SEARCH=false when an organisation forbids it.
    keyless_search_configured: bool = False

    @property
    def web_search_configured(self) -> bool:
        return (
            self.google_search_configured
            or self.evidence_provider_configured
            or self.keyless_search_configured
        )


class _DuckDuckGoResultParser(HTMLParser):
    """Minimal parser for the DuckDuckGo HTML endpoint (no JavaScript, no key)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._field: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key: (value or "") for key, value in attrs}
        classes = attributes.get("class", "")
        if tag == "a" and "result__a" in classes:
            self._current = {"title": "", "url": attributes.get("href", ""), "snippet": ""}
            self._field = "title"
        elif tag == "a" and "result__snippet" in classes and self._current is not None:
            self._field = "snippet"

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._field == "title" and self._current is not None:
            self._field = None
        elif tag == "a" and self._field == "snippet" and self._current is not None:
            self.results.append(self._current)
            self._current = None
            self._field = None

    def handle_data(self, data: str) -> None:
        if self._current is not None and self._field:
            self._current[self._field] += data


class DuckDuckGoSearchProvider:
    """Keyless web discovery (DuckDuckGo HTML first, Bing HTML as fallback).

    No API key is required. Results are discovery records only. ORBYTHRA still
    fetches the underlying public HTTPS page through the V5.1 web-evidence
    controls before anything can count as direct evidence for a VERIFIED answer.
    Some shared egress IPs are rate-limited by DuckDuckGo (HTTP 202 "anomaly"
    page); in that case the Bing HTML result page is parsed instead.
    """

    ddg_endpoint = "https://html.duckduckgo.com/html/"
    bing_endpoint = "https://www.bing.com/search"
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 ORBYTHRA-Discovery/23"
    )

    def search(self, query: str, *, limit: int = 5, timeout: float = 12.0) -> list[dict[str, Any]]:
        limit = max(1, min(10, int(limit)))
        query = query.strip()[:500]
        errors: list[str] = []
        for engine in ("duckduckgo", "bing"):
            try:
                rows = self._duckduckgo(query, timeout) if engine == "duckduckgo" else self._bing(query, timeout)
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
                errors.append(f"{engine}:{exc.__class__.__name__}")
                continue
            normalized = self._normalize(rows, engine, limit)
            if normalized:
                return normalized
            errors.append(f"{engine}:no_results")
        raise RuntimeError("keyless_search_failed:" + ",".join(errors))

    def _get(self, url: str, timeout: float) -> str:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html",
                "Accept-Language": "en;q=0.9,tr;q=0.8",
            },
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(2_000_000)
        return raw.decode("utf-8", errors="replace")

    def _duckduckgo(self, query: str, timeout: float) -> list[dict[str, str]]:
        params = {"q": query, "kl": os.getenv("ORBYTHRA_KEYLESS_SEARCH_REGION", "wt-wt")}
        page = self._get(f"{self.ddg_endpoint}?{urllib.parse.urlencode(params)}", timeout)
        parser = _DuckDuckGoResultParser()
        parser.feed(page)
        for row in parser.results:
            row["url"] = self._resolve_redirect(row.get("url", ""))
        return parser.results

    def _bing(self, query: str, timeout: float) -> list[dict[str, str]]:
        params = {"q": query, "setlang": "en", "count": "10"}
        page = self._get(f"{self.bing_endpoint}?{urllib.parse.urlencode(params)}", timeout)
        rows: list[dict[str, str]] = []
        for block in _BING_RESULT.finditer(page):
            body = block.group(1)
            anchor = _BING_ANCHOR.search(body)
            if not anchor:
                continue
            snippet = _BING_SNIPPET.search(body)
            rows.append({
                "url": self._resolve_bing_url(html.unescape(anchor.group(1))),
                "title": html.unescape(_TAG.sub("", anchor.group(2))),
                "snippet": html.unescape(_TAG.sub("", snippet.group(1))) if snippet else "",
            })
        return rows

    @staticmethod
    def _normalize(rows: list[dict[str, str]], engine: str, limit: int) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            url = row.get("url", "")
            title = " ".join(row.get("title", "").split())
            if not url.startswith("http") or not title or url in seen:
                continue
            seen.add(url)
            publisher = urllib.parse.urlparse(url).hostname or ""
            normalized.append({
                "source_id": f"{engine}-{len(normalized) + 1}",
                "title": title[:500],
                "url": url[:2000],
                "publisher": publisher[:300],
                "snippet": " ".join(row.get("snippet", "").split())[:4000],
                "source_type": f"{engine}_html",
            })
            if len(normalized) >= limit:
                break
        return normalized

    @staticmethod
    def _resolve_redirect(href: str) -> str:
        # DuckDuckGo wraps outbound links as //duckduckgo.com/l/?uddg=<encoded-url>&rut=...
        if href.startswith("//"):
            href = "https:" + href
        parsed = urllib.parse.urlparse(href)
        if "duckduckgo.com" in (parsed.hostname or "") and parsed.path.startswith("/l/"):
            target = urllib.parse.parse_qs(parsed.query).get("uddg", [""])[0]
            return urllib.parse.unquote(target)
        return href

    @staticmethod
    def _resolve_bing_url(href: str) -> str:
        # Bing wraps outbound links as https://www.bing.com/ck/a?...&u=a1<base64url-url>&...
        parsed = urllib.parse.urlparse(href)
        if "bing.com" in (parsed.hostname or "") and parsed.path.startswith("/ck/"):
            encoded = urllib.parse.parse_qs(parsed.query).get("u", [""])[0]
            if encoded.startswith("a1"):
                payload = encoded[2:]
                payload += "=" * (-len(payload) % 4)
                try:
                    return base64.urlsafe_b64decode(payload).decode("utf-8", errors="replace")
                except (ValueError, binascii.Error):
                    return ""
        return href


_TAG = re.compile(r"<[^>]+>")
_BING_RESULT = re.compile(r'<li class="b_algo"(.*?)</li>', re.S)
_BING_ANCHOR = re.compile(r'<h2[^>]*><a[^>]*href="([^"]+)"[^>]*>(.*?)</a></h2>', re.S)
_BING_SNIPPET = re.compile(r"<p[^>]*>(.*?)</p>", re.S)


class JsonHttpProvider:
    def __init__(self, base_url: str, token_env: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token_env = token_env

    def post_json(self, path: str, payload: dict[str, Any], timeout: float = 20.0) -> dict[str, Any]:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        token = os.getenv(self.token_env, "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(
            f"{self.base_url}/{path.lstrip('/')}" ,
            data=data,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
        parsed = json.loads(body)
        if not isinstance(parsed, dict):
            raise ValueError("provider_response_must_be_object")
        return parsed


class SerpApiSearchProvider:
    """Server-side SerpAPI adapter for Google organic search results.

    The API key stays on the backend. Search results are discovery records only;
    ORBYTHRA still fetches the underlying pages and applies its evidence gates
    before a factual answer can become VERIFIED/PASS.
    """

    endpoint = "https://serpapi.com/search.json"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def search(self, query: str, *, limit: int = 5, timeout: float = 15.0) -> list[dict[str, Any]]:
        limit = max(1, min(10, int(limit)))
        params: dict[str, Any] = {
            "engine": "google",
            "q": query,
            "api_key": self.api_key,
            "num": limit,
            "safe": "active",
        }
        hl = os.getenv("SERPAPI_HL", "").strip()
        gl = os.getenv("SERPAPI_GL", "").strip()
        location = os.getenv("SERPAPI_LOCATION", "").strip()
        if hl:
            params["hl"] = hl
        if gl:
            params["gl"] = gl
        if location:
            params["location"] = location

        request = urllib.request.Request(
            f"{self.endpoint}?{urllib.parse.urlencode(params)}",
            headers={"Accept": "application/json", "User-Agent": "ORBYTHRA/11 UnifiedAnswer"},
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            parsed = json.loads(response.read().decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("serpapi_response_must_be_object")
        if parsed.get("error"):
            raise RuntimeError("serpapi_search_failed")

        items = parsed.get("organic_results", [])
        if not isinstance(items, list):
            items = []
        out: list[dict[str, Any]] = []
        for index, item in enumerate(items[:limit], start=1):
            if not isinstance(item, dict):
                continue
            url = str(item.get("link") or "").strip()
            if not url:
                continue
            publisher = str(item.get("source") or item.get("displayed_link") or "")[:300]
            out.append({
                "source_id": f"serpapi-google-{index}",
                "title": str(item.get("title") or url)[:500],
                "url": url[:2000],
                "publisher": publisher,
                "snippet": str(item.get("snippet") or "")[:4000],
                "published_at": str(item.get("date") or "")[:120] or None,
                "source_type": "serpapi_google",
            })
        return out


class GoogleSearchProvider:
    """Server-side Google Programmable Search adapter.

    Credentials never enter the browser bundle. The normalized result is only a
    discovery record; callers should fetch/verify the underlying source before
    treating a claim as established.
    """

    endpoint = "https://customsearch.googleapis.com/customsearch/v1"

    def __init__(self, api_key: str, engine_id: str) -> None:
        self.api_key = api_key
        self.engine_id = engine_id

    def search(self, query: str, *, limit: int = 5, timeout: float = 10.0) -> list[dict[str, Any]]:
        limit = max(1, min(10, int(limit)))
        params = urllib.parse.urlencode({
            "key": self.api_key,
            "cx": self.engine_id,
            "q": query,
            "num": limit,
            "safe": "active",
        })
        request = urllib.request.Request(
            f"{self.endpoint}?{params}",
            headers={"Accept": "application/json", "User-Agent": "ORBYTHRA/11 UnifiedAnswer"},
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            parsed = json.loads(response.read().decode("utf-8"))
        items = parsed.get("items", []) if isinstance(parsed, dict) else []
        out: list[dict[str, Any]] = []
        for index, item in enumerate(items[:limit], start=1):
            if not isinstance(item, dict):
                continue
            url = str(item.get("link") or "").strip()
            if not url:
                continue
            out.append({
                "source_id": f"google-{index}",
                "title": str(item.get("title") or url)[:500],
                "url": url[:2000],
                "publisher": str(item.get("displayLink") or "")[:300],
                "snippet": str(item.get("snippet") or "")[:4000],
                "source_type": "google_programmable_search",
            })
        return out


def _serpapi_key() -> str:
    return (
        os.getenv("SERPAPI_API_KEY", "").strip()
        or os.getenv("SERPAPI_KEY", "").strip()
    )


def status() -> ProviderStatus:
    serpapi_configured = bool(_serpapi_key())
    programmable_google_configured = bool(
        os.getenv("GOOGLE_SEARCH_API_KEY", "").strip()
        and os.getenv("GOOGLE_SEARCH_ENGINE_ID", "").strip()
    )
    return ProviderStatus(
        evidence_provider_configured=bool(SETTINGS.evidence_provider_url),
        llm_provider_configured=bool(SETTINGS.llm_provider_url),
        google_search_configured=serpapi_configured or programmable_google_configured,
        serpapi_search_configured=serpapi_configured,
        keyless_search_configured=keyless_search_enabled(),
    )


def keyless_search_enabled() -> bool:
    return os.getenv("ORBYTHRA_KEYLESS_SEARCH", "true").strip().lower() not in {"0", "false", "no", "off"}


def keyless_search_provider() -> DuckDuckGoSearchProvider | None:
    return DuckDuckGoSearchProvider() if keyless_search_enabled() else None


def evidence_provider() -> JsonHttpProvider | None:
    if not SETTINGS.evidence_provider_url:
        return None
    return JsonHttpProvider(SETTINGS.evidence_provider_url, "ORBYTHRA_EVIDENCE_PROVIDER_TOKEN")


def llm_provider() -> JsonHttpProvider | None:
    if not SETTINGS.llm_provider_url:
        return None
    return JsonHttpProvider(SETTINGS.llm_provider_url, "ORBYTHRA_LLM_PROVIDER_TOKEN")


def google_search_provider() -> SerpApiSearchProvider | GoogleSearchProvider | None:
    # SerpAPI is the preferred Google discovery provider when configured because
    # it needs only one server-side API key and returns normalized organic data.
    serpapi_key = _serpapi_key()
    if serpapi_key:
        return SerpApiSearchProvider(serpapi_key)

    api_key = os.getenv("GOOGLE_SEARCH_API_KEY", "").strip()
    engine_id = os.getenv("GOOGLE_SEARCH_ENGINE_ID", "").strip()
    if not api_key or not engine_id:
        return None
    return GoogleSearchProvider(api_key, engine_id)
