from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from ai_research_council import fetch_ai_research_council


@dataclass(frozen=True)
class ProviderSpec:
    provider_id: str
    domains: tuple[str, ...]
    description: str
    transport: str
    keywords: tuple[str, ...] = ()
    provider: str = "configured"
    priority: int = 50
    fallback: bool = False
    freshness: str = "mixed"
    read_only: bool = True
    auto_execute: bool = True
    url: str | None = None
    url_env: str | None = None
    api_key_env: str | None = None
    api_key_required: bool = False
    api_key_header: str = "Authorization"
    api_key_prefix: str = "Bearer "
    query_param: str = "query"
    static_params: tuple[tuple[str, str], ...] = ()
    commercial_use: str = "review"
    terms_url: str = "connector://provider"
    attribution: str = "Preserve provider and upstream source attribution."


def _gateway(
    provider_id: str,
    *,
    domains: tuple[str, ...],
    keywords: tuple[str, ...],
    url_env: str,
    api_key_env: str,
    priority: int = 85,
    fallback: bool = False,
) -> ProviderSpec:
    return ProviderSpec(
        provider_id=provider_id,
        domains=domains,
        description=f"Configured read-only {provider_id.replace('_', ' ')} provider.",
        transport="standard_post_json",
        keywords=keywords,
        provider=f"configured_{provider_id}",
        priority=priority,
        fallback=fallback,
        freshness="fresh",
        url_env=url_env,
        api_key_env=api_key_env,
        terms_url=f"connector://{provider_id}",
    )


BUILTIN_PROVIDERS: dict[str, ProviderSpec] = {
    "general_web": _gateway(
        "general_web",
        domains=("general", "web", "news"),
        keywords=(),
        url_env="FUSION_WEB_SEARCH_URL",
        api_key_env="FUSION_WEB_SEARCH_API_KEY",
        priority=20,
        fallback=True,
    ),
    "sports": _gateway(
        "sports",
        domains=("sports",),
        keywords=(
            "maç", "skor", "futbol", "basketbol", "fixture", "match", "score",
            "odds", "xg", "form", "sakat", "injury", "standings", "puan durumu",
        ),
        url_env="FUSION_SPORTS_URL",
        api_key_env="FUSION_SPORTS_API_KEY",
        priority=96,
    ),
    "finance": _gateway(
        "finance",
        domains=("finance", "markets", "stocks"),
        keywords=(
            "hisse", "borsa", "stock", "share", "ticker", "nasdaq", "nyse",
            "market cap", "fiyat", "price",
        ),
        url_env="FUSION_FINANCE_URL",
        api_key_env="FUSION_FINANCE_API_KEY",
        priority=97,
    ),
    "crypto": _gateway(
        "crypto",
        domains=("crypto", "blockchain"),
        keywords=(
            "kripto", "crypto", "bitcoin", "ethereum", "token", "coin", "dex",
            "blockchain", "chain",
        ),
        url_env="FUSION_CRYPTO_URL",
        api_key_env="FUSION_CRYPTO_API_KEY",
        priority=97,
    ),
    "news": _gateway(
        "news",
        domains=("news", "current_events"),
        keywords=("haber", "news", "son dakika", "breaking", "gelişme", "development"),
        url_env="FUSION_NEWS_URL",
        api_key_env="FUSION_NEWS_API_KEY",
        priority=93,
    ),
    "science": _gateway(
        "science",
        domains=("science", "research", "academic"),
        keywords=(
            "araştırma", "research", "paper", "makale", "academic", "bilimsel",
            "study", "doi",
        ),
        url_env="FUSION_SCIENCE_URL",
        api_key_env="FUSION_SCIENCE_API_KEY",
        priority=92,
    ),
    "patents": _gateway(
        "patents",
        domains=("patents", "intellectual_property"),
        keywords=("patent", "patentler", "filing", "invention", "buluş"),
        url_env="FUSION_PATENTS_URL",
        api_key_env="FUSION_PATENTS_API_KEY",
        priority=95,
    ),
    "companies": _gateway(
        "companies",
        domains=("companies", "business"),
        keywords=(
            "şirket", "company", "firma", "startup", "revenue", "gelir", "funding",
            "yatırım turu",
        ),
        url_env="FUSION_COMPANIES_URL",
        api_key_env="FUSION_COMPANIES_API_KEY",
        priority=91,
    ),
    "legal": _gateway(
        "legal",
        domains=("legal", "regulation"),
        keywords=("kanun", "law", "legal", "mevzuat", "regulation", "mahkeme", "court"),
        url_env="FUSION_LEGAL_URL",
        api_key_env="FUSION_LEGAL_API_KEY",
        priority=91,
    ),
    "real_estate": _gateway(
        "real_estate",
        domains=("real_estate", "property"),
        keywords=(
            "gayrimenkul", "emlak", "arsa", "parsel", "property", "real estate",
            "konut", "daire",
        ),
        url_env="FUSION_REAL_ESTATE_URL",
        api_key_env="FUSION_REAL_ESTATE_API_KEY",
        priority=94,
    ),
    "vehicles": _gateway(
        "vehicles",
        domains=("vehicles", "automotive"),
        keywords=("araba", "otomobil", "araç", "vehicle", "car", "ilan", "model yılı"),
        url_env="FUSION_VEHICLES_URL",
        api_key_env="FUSION_VEHICLES_API_KEY",
        priority=89,
    ),
    "jobs": _gateway(
        "jobs",
        domains=("jobs", "careers"),
        keywords=("iş ilanı", "job", "jobs", "kariyer", "career", "hiring", "internship", "staj"),
        url_env="FUSION_JOBS_URL",
        api_key_env="FUSION_JOBS_API_KEY",
        priority=91,
    ),
    "travel": _gateway(
        "travel",
        domains=("travel", "tourism"),
        keywords=("seyahat", "travel", "otel", "hotel", "uçak bileti", "rota", "itinerary"),
        url_env="FUSION_TRAVEL_URL",
        api_key_env="FUSION_TRAVEL_API_KEY",
        priority=89,
    ),
    "shopping": _gateway(
        "shopping",
        domains=("shopping", "products"),
        keywords=(
            "satın al", "buy", "ürün", "product", "alışveriş", "shopping",
            "fiyat karşılaştır", "compare price",
        ),
        url_env="FUSION_SHOPPING_URL",
        api_key_env="FUSION_SHOPPING_API_KEY",
        priority=89,
    ),
    "social": _gateway(
        "social",
        domains=("social", "public_posts"),
        keywords=("sosyal medya", "social media", "trend", "viral", "reddit", "forum", "public post"),
        url_env="FUSION_SOCIAL_URL",
        api_key_env="FUSION_SOCIAL_API_KEY",
        priority=87,
    ),
    "places": _gateway(
        "places",
        domains=("places", "maps", "local"),
        keywords=(
            "yakınımda", "near me", "adres", "address", "mekan", "place", "restaurant",
            "restoran", "harita", "map", "konum", "location",
        ),
        url_env="FUSION_PLACES_URL",
        api_key_env="FUSION_PLACES_API_KEY",
        priority=93,
    ),
    "wikipedia_tr": ProviderSpec(
        provider_id="wikipedia_tr",
        domains=("general", "encyclopedia"),
        description="Live Turkish Wikipedia search API.",
        transport="get_json",
        keywords=("kimdir", "nedir", "hakkında", "tarih", "history", "who is", "what is"),
        provider="wikipedia",
        priority=58,
        freshness="stable",
        url="https://tr.wikipedia.org/w/api.php",
        query_param="srsearch",
        static_params=(("action", "query"), ("list", "search"), ("format", "json"), ("utf8", "1"), ("srlimit", "8")),
        terms_url="https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use",
        attribution="Preserve Wikimedia/Wikipedia attribution and source links.",
    ),
    "openalex": ProviderSpec(
        provider_id="openalex",
        domains=("science", "research", "academic"),
        description="Live OpenAlex scholarly works search.",
        transport="get_json",
        keywords=("araştırma", "research", "paper", "makale", "academic", "bilimsel", "study"),
        provider="openalex",
        priority=80,
        freshness="mixed",
        url="https://api.openalex.org/works",
        query_param="search",
        static_params=(("per-page", "8"),),
        terms_url="https://docs.openalex.org/",
        attribution="Preserve OpenAlex work/source identifiers and attribution.",
    ),
    "crossref": ProviderSpec(
        provider_id="crossref",
        domains=("science", "research", "academic"),
        description="Live Crossref scholarly metadata search.",
        transport="get_json",
        keywords=("araştırma", "research", "paper", "makale", "doi", "academic", "bilimsel"),
        provider="crossref",
        priority=78,
        freshness="mixed",
        url="https://api.crossref.org/works",
        query_param="query",
        static_params=(("rows", "8"),),
        terms_url="https://www.crossref.org/terms/",
        attribution="Preserve DOI and publisher/source attribution.",
    ),
    "osm_nominatim": ProviderSpec(
        provider_id="osm_nominatim",
        domains=("places", "maps", "travel"),
        description="Live OpenStreetMap Nominatim place search.",
        transport="get_json",
        keywords=("adres", "address", "konum", "location", "mekan", "place", "harita", "map"),
        provider="openstreetmap_nominatim",
        priority=76,
        freshness="mixed",
        url="https://nominatim.openstreetmap.org/search",
        query_param="q",
        static_params=(("format", "jsonv2"), ("limit", "8"), ("addressdetails", "1")),
        terms_url="https://operations.osmfoundation.org/policies/nominatim/",
        attribution="Attribute OpenStreetMap contributors and respect Nominatim usage policy.",
    ),
    "hn_algolia": ProviderSpec(
        provider_id="hn_algolia",
        domains=("technology", "startups", "public_news"),
        description="Live Hacker News search via Algolia public API.",
        transport="get_json",
        keywords=("startup", "hacker news", "y combinator", "technology", "teknoloji", "developer", "yazılım"),
        provider="hn_algolia",
        priority=70,
        freshness="fresh",
        url="https://hn.algolia.com/api/v1/search",
        query_param="query",
        static_params=(("hitsPerPage", "8"),),
        terms_url="https://hn.algolia.com/api",
        attribution="Preserve original Hacker News item links and authorship.",
    ),
}


def _manifest_dir() -> Path:
    configured = os.getenv("FUSION_PROVIDER_DIR", "").strip()
    return Path(configured) if configured else Path(__file__).resolve().parent / "provider_manifests"


def _from_payload(payload: dict[str, Any]) -> ProviderSpec:
    provider_id = str(payload["provider_id"]).strip().lower()
    if not re.fullmatch(r"[a-z0-9_-]{2,64}", provider_id):
        raise ValueError("Invalid provider_id")
    domains_raw = payload.get("domains", ["custom"])
    domains = (domains_raw.lower(),) if isinstance(domains_raw, str) else tuple(str(item).lower() for item in domains_raw)
    params_raw = payload.get("static_params", {})
    if isinstance(params_raw, dict):
        static_params = tuple((str(key), str(value)) for key, value in params_raw.items())
    else:
        static_params = tuple((str(item[0]), str(item[1])) for item in params_raw)
    return ProviderSpec(
        provider_id=provider_id,
        domains=domains,
        description=str(payload.get("description", "Custom read-only provider")),
        transport=str(payload.get("transport", "standard_post_json")),
        keywords=tuple(str(item).lower() for item in payload.get("keywords", [])),
        provider=str(payload.get("provider", provider_id)),
        priority=int(payload.get("priority", 50)),
        fallback=bool(payload.get("fallback", False)),
        freshness=str(payload.get("freshness", "mixed")),
        read_only=bool(payload.get("read_only", True)),
        auto_execute=bool(payload.get("auto_execute", True)),
        url=str(payload.get("url") or "") or None,
        url_env=str(payload.get("url_env") or "") or None,
        api_key_env=str(payload.get("api_key_env") or "") or None,
        api_key_required=bool(payload.get("api_key_required", False)),
        api_key_header=str(payload.get("api_key_header", "Authorization")),
        api_key_prefix=str(payload.get("api_key_prefix", "Bearer ")),
        query_param=str(payload.get("query_param", "query")),
        static_params=static_params,
        commercial_use=str(payload.get("commercial_use", "review")),
        terms_url=str(payload.get("terms_url", f"connector://{provider_id}")),
        attribution=str(payload.get("attribution", "Preserve provider and upstream source attribution.")),
    )


def _load_manifests() -> dict[str, ProviderSpec]:
    specs: dict[str, ProviderSpec] = {}
    directory = _manifest_dir()
    if not directory.exists():
        return specs
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("providers"), list):
                rows = payload["providers"]
            elif isinstance(payload, list):
                rows = payload
            else:
                rows = [payload]
            for row in rows:
                if isinstance(row, dict):
                    spec = _from_payload(row)
                    specs[spec.provider_id] = spec
        except (OSError, ValueError, TypeError, KeyError):
            continue
    return specs


def provider_specs() -> dict[str, ProviderSpec]:
    specs = dict(BUILTIN_PROVIDERS)
    specs.update(_load_manifests())
    return specs


def _url(spec: ProviderSpec) -> str:
    if spec.url:
        return spec.url
    if spec.url_env:
        return os.getenv(spec.url_env, "").strip()
    return ""


def provider_ready(spec: ProviderSpec) -> bool:
    if not spec.read_only or not spec.auto_execute:
        return False
    if spec.transport not in {"standard_post_json", "get_json"}:
        return False
    if not _url(spec):
        return False
    if spec.api_key_required and spec.api_key_env:
        return bool(os.getenv(spec.api_key_env, "").strip())
    return True


def _fanout() -> int:
    try:
        value = int(os.getenv("FUSION_PROVIDER_FANOUT", "3"))
    except ValueError:
        value = 3
    return min(5, max(1, value))


def _score(query: str, spec: ProviderSpec) -> int:
    q = query.lower()
    hits = sum(1 for keyword in spec.keywords if keyword and keyword in q)
    return hits * 1000 + spec.priority


def matching_providers(query: str, *, ready_only: bool = True) -> list[ProviderSpec]:
    ranked: list[tuple[int, ProviderSpec]] = []
    for spec in provider_specs().values():
        score = _score(query, spec)
        if score < 1000:
            continue
        if ready_only and not provider_ready(spec):
            continue
        ranked.append((score, spec))
    ranked.sort(key=lambda item: (-item[0], item[1].provider_id))
    return [spec for _, spec in ranked]


def route_providers(query: str) -> list[ProviderSpec]:
    matched = matching_providers(query, ready_only=True)
    if matched:
        return matched[:_fanout()]
    fallbacks = [spec for spec in provider_specs().values() if spec.fallback and provider_ready(spec)]
    fallbacks.sort(key=lambda spec: (-spec.priority, spec.provider_id))
    return fallbacks[:_fanout()]


def provider_domains_for_query(query: str) -> list[str]:
    domains: list[str] = []
    for spec in matching_providers(query, ready_only=False):
        for domain in spec.domains:
            if domain not in domains:
                domains.append(domain)
    return domains


def provider_gap_messages(query: str) -> list[str]:
    if route_providers(query):
        return []
    missing: list[str] = []
    for spec in matching_providers(query, ready_only=False):
        if spec.url_env and not _url(spec):
            missing.append(spec.url_env)
    general = provider_specs().get("general_web")
    if general and general.url_env and not provider_ready(general):
        missing.append(general.url_env)
    domains = provider_domains_for_query(query)
    domain_text = ", ".join(domains) if domains else "general external research"
    required = ", ".join(dict.fromkeys(missing)) or "a trusted read-only provider"
    return [f"No ready provider for {domain_text}; configure one of: {required}"]


def provider_catalog() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in sorted(provider_specs().values(), key=lambda item: item.provider_id):
        row = asdict(spec)
        row["ready"] = provider_ready(spec)
        row["configured_url"] = bool(_url(spec))
        row["missing_configuration"] = []
        if not _url(spec):
            row["missing_configuration"].append(spec.url_env or "provider URL")
        if spec.api_key_required and spec.api_key_env and not os.getenv(spec.api_key_env, "").strip():
            row["missing_configuration"].append(spec.api_key_env)
        rows.append(row)
    return rows


def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme == "https":
        return
    if parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        return
    raise PermissionError("Provider URL must use HTTPS, except localhost development endpoints")


def _headers(spec: ProviderSpec) -> dict[str, str]:
    headers = {"User-Agent": "ORBYTHRA/1.3 read-only provider federation"}
    if spec.api_key_env:
        api_key = os.getenv(spec.api_key_env, "").strip()
        if api_key:
            headers[spec.api_key_header] = f"{spec.api_key_prefix}{api_key}"
    return headers


async def _fetch_one(
    spec: ProviderSpec,
    *,
    query: str,
    scope: dict[str, Any],
    timeout: float,
    max_response_bytes: int,
) -> dict[str, Any]:
    url = _url(spec)
    _validate_url(url)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            if spec.transport == "standard_post_json":
                response = await client.post(
                    url,
                    json={"query": query, "scope": scope, "mode": "read_only"},
                    headers=_headers(spec),
                )
            elif spec.transport == "get_json":
                params = dict(spec.static_params)
                params[spec.query_param] = query
                response = await client.get(url, params=params, headers=_headers(spec))
            else:
                raise PermissionError(f"Unsupported provider transport: {spec.transport}")
            response.raise_for_status()
            if len(response.content) > max_response_bytes:
                raise ValueError("Provider response exceeds configured evidence limit")
            content_type = response.headers.get("content-type", "")
            if "json" not in content_type.lower() and response.content.strip()[:1] not in {b"{", b"["}:
                raise ValueError("Provider returned non-JSON content")
            payload = response.json()
        return {
            "ok": True,
            "provider_id": spec.provider_id,
            "provider": spec.provider,
            "domains": list(spec.domains),
            "freshness": spec.freshness,
            "source_url": url,
            "payload": payload,
        }
    except Exception as exc:
        return {
            "ok": False,
            "provider_id": spec.provider_id,
            "provider": spec.provider,
            "domains": list(spec.domains),
            "source_url": url,
            "error": f"{type(exc).__name__}: {exc}",
        }


async def fetch_federated(
    query: str,
    scope: dict[str, Any],
    *,
    timeout: float,
    max_response_bytes: int,
) -> dict[str, Any]:
    selected = route_providers(query)
    provider_task = asyncio.gather(
        *(
            _fetch_one(
                spec,
                query=query,
                scope=scope,
                timeout=timeout,
                max_response_bytes=max_response_bytes,
            )
            for spec in selected
        )
    )
    council_task = fetch_ai_research_council(
        query,
        timeout=timeout,
        max_response_bytes=max_response_bytes,
    )
    provider_results, council = await asyncio.gather(provider_task, council_task)
    council_results = council.get("results", []) if isinstance(council, dict) else []
    results = list(provider_results) + list(council_results)
    if not selected and not council.get("engines_used"):
        return {
            "status": "provider_required",
            "query": query,
            "provider_domains": provider_domains_for_query(query),
            "provider_gaps": provider_gap_messages(query),
            "providers_used": [],
            "ai_engines_used": [],
            "ai_research": council,
            "results": [],
        }
    return {
        "status": "ok" if any(item.get("ok") for item in results) else "provider_failure",
        "query": query,
        "provider_domains": provider_domains_for_query(query),
        "providers_used": [spec.provider_id for spec in selected],
        "ai_engines_used": council.get("engines_used", []),
        "ai_research": council,
        "results": results,
    }
