from __future__ import annotations

import json
import re
from typing import Any

from capabilities import (
    auto_tool_names,
    infer_capability_names,
    likely_requires_external_data,
    resolve_capability_gap,
)
from config import get_settings
from llm import ModelRouter
from osiris_client import READ_ONLY_TOOLS, normalize_tool_name
from providers import route_providers
from schemas import InvestigationPlan
from source_policy import enforce_source_policy

KEYWORD_TOOL_MAP = {
    "deprem": "earthquakes",
    "earthquake": "earthquakes",
    "yangın": "fires",
    "fire": "fires",
    "uçuş": "flights",
    "uçak": "flights",
    "flight": "flights",
    "hava durumu": "weather",
    "weather": "weather",
    "hava kalitesi": "air_quality",
    "air quality": "air_quality",
    "uydu": "satellites",
    "satellite": "satellites",
    "uzay havası": "space_weather",
    "space weather": "space_weather",
    "radar": "radar",
    "çatışma": "conflicts",
    "conflict": "conflicts",
    "cephe": "frontlines",
    "frontline": "frontlines",
    "gdelt": "gdelt",
    "ülke riski": "country_risk",
    "country risk": "country_risk",
    "haber": "news",
    "news": "news",
    "piyasa": "markets",
    "market": "markets",
    "kripto": "crypto",
    "crypto": "crypto",
    "kamera": "cctv",
    "cctv": "cctv",
    "altyapı": "infrastructure",
    "infrastructure": "infrastructure",
    "deniz": "maritime",
    "maritime": "maritime",
    "gemi": "maritime",
    "siber saldırı": "cyber_attacks",
    "cyber attack": "cyber_attacks",
    "siber": "cyber_threats",
    "cyber": "cyber_threats",
    "zararlı yazılım": "malware",
    "malware": "malware",
}

OSINT_BROAD_TERMS = {
    "olağandışı",
    "anomali",
    "risk",
    "tehdit",
    "olay",
    "gelişme",
    "brief",
    "intelligence",
    "osint",
    "ülke",
    "bölge",
    "region",
    "threat",
    "incident",
}
DEFAULT_TOOL_SET = {
    "earthquakes",
    "fires",
    "weather",
    "gdelt",
    "news",
    "country_risk",
}
LOCAL_ONLY_CAPABILITIES = {"calculator", "direct_reasoning"}


def infer_question_type(query: str) -> str:
    q = query.lower()
    if any(word in q for word in ("korelasyon", "ilişki", "correlation", "bağlantı")):
        return "correlation"
    if any(word in q for word in ("anomali", "olağandışı", "anomaly", "unusual")):
        return "anomaly"
    if any(word in q for word in ("karşılaştır", "compare", "versus", " vs ")):
        return "comparison"
    if any(word in q for word in ("risk", "tehdit", "threat")):
        return "risk"
    if any(word in q for word in ("özet", "brief", "gelişme", "neler oldu")):
        return "briefing"
    return "lookup"


def infer_time_range(query: str) -> str | None:
    q = query.lower()
    patterns = [
        (r"son\s+(\d+)\s*saat", lambda m: f"PT{m.group(1)}H"),
        (r"last\s+(\d+)\s*hours?", lambda m: f"PT{m.group(1)}H"),
        (r"son\s+(\d+)\s*gün", lambda m: f"P{m.group(1)}D"),
        (r"last\s+(\d+)\s*days?", lambda m: f"P{m.group(1)}D"),
    ]
    for pattern, formatter in patterns:
        match = re.search(pattern, q)
        if match:
            return formatter(match)
    if "bugün" in q or "today" in q:
        return "P1D"
    if "bu hafta" in q or "this week" in q:
        return "P7D"
    return None


def deterministic_tools(
    query: str,
    requested_tools: list[str] | None = None,
) -> list[str]:
    settings = get_settings()
    q = query.lower()
    available = auto_tool_names()

    native = {
        tool
        for keyword, tool in KEYWORD_TOOL_MAP.items()
        if keyword in q and tool in available
    }
    inferred = infer_capability_names(query)
    capabilities = {name for name in inferred if name in available}
    selected = native | capabilities

    local_only = bool(selected) and selected.issubset(LOCAL_ONLY_CAPABILITIES)
    providers = route_providers(query)
    if providers and "provider_federation" in available and not local_only:
        selected.add("provider_federation")

    if not selected and any(term in q for term in OSINT_BROAD_TERMS):
        selected = DEFAULT_TOOL_SET & available

    if (
        not selected
        and likely_requires_external_data(query)
        and "provider_federation" in available
    ):
        selected = {"provider_federation"}

    # Universal Deep Search: arbitrary factual lookups default to external
    # evidence rather than model memory. Explicit local tasks were selected
    # above and therefore do not reach this branch.
    if not selected and "provider_federation" in available:
        selected = {"provider_federation"}

    if not selected:
        selected = {"direct_reasoning"} if "direct_reasoning" in available else set()

    if requested_tools is not None:
        requested = {normalize_tool_name(tool) for tool in requested_tools}
        unknown = requested.difference(available)
        if unknown:
            raise PermissionError(
                "Unknown, unavailable, or non-read-only tools requested: "
                f"{sorted(unknown)}"
            )
        selected &= requested
        if not selected and requested:
            selected = requested

    return sorted(selected)[: settings.max_tool_calls]


async def build_plan(
    query: str,
    requested_tools: list[str] | None,
    scope: dict[str, Any],
) -> tuple[InvestigationPlan, dict[str, str]]:
    settings = get_settings()
    available = auto_tool_names()
    tools = deterministic_tools(query, requested_tools)
    caller_region = scope.get("region")
    caller_time_range = scope.get("time_range")
    region = caller_region
    time_range = caller_time_range or infer_time_range(query)
    question_type = infer_question_type(query)
    model_meta = {"provider": "deterministic", "model": "provider-federation-router-v3-deep"}
    deterministic_external = "provider_federation" in tools

    if settings.ai_planner_enabled and requested_tools is None:
        system = (
            "You are ORBYTHRA's bilingual Universal Deep Search planner. Return only "
            "JSON matching the schema. Select only from AVAILABLE_TOOLS and use the "
            "smallest sufficient set. provider_federation is the domain-agnostic "
            "external research capability: it fans out across trusted read-only global "
            "providers and may use Turkish and English reference sources, scientific "
            "indexes, current-event sources and domain providers. Do not invent "
            "provider-specific tool names. Use direct_reasoning only for drafting, "
            "rewriting, translation, ideation and stable reasoning tasks. For factual "
            "lookup or research, select provider_federation when native ORBYTHRA feeds "
            "are insufficient. Never substitute model memory for fresh or verifiable "
            "facts. Never request active scanning, exploitation, credential access, "
            "facial tracking or intrusive surveillance."
        )
        prompt = (
            f"QUERY: {query}\n"
            f"USER_SCOPE: {json.dumps(scope, ensure_ascii=False)}\n"
            f"AVAILABLE_TOOLS: {', '.join(sorted(available))}\n"
            f"MAX_TOOL_CALLS: {settings.max_tool_calls}\n"
            "The user can ask in Turkish or English. External providers are hidden "
            "behind provider_federation. Sports, finance, crypto, science, patents, "
            "companies, legal, real estate, vehicles, jobs, travel, shopping, social, "
            "places, global news and general knowledge are provider domains, not "
            "separate autonomous tool contracts."
        )
        try:
            payload, model_result = await ModelRouter().generate_json(
                system,
                prompt,
                InvestigationPlan.model_json_schema(),
            )
            candidate = InvestigationPlan.model_validate(payload)
            normalized = [normalize_tool_name(item) for item in candidate.tools]
            valid = [item for item in normalized if item in available]
            if valid:
                external_tools = set(READ_ONLY_TOOLS) | {"provider_federation"}
                if deterministic_external and not any(
                    item in external_tools for item in valid
                ):
                    valid = ["provider_federation"]
                tools = valid[: settings.max_tool_calls]
                if not caller_region:
                    region = candidate.region or region
                if not caller_time_range:
                    time_range = candidate.time_range or time_range
                question_type = candidate.question_type
                model_meta = {
                    "provider": model_result.provider,
                    "model": model_result.model,
                }
        except Exception:
            pass

    allowed, warnings = enforce_source_policy(tools)
    gaps = resolve_capability_gap(query, infer_capability_names(query))
    if tools and not allowed:
        detail = "; ".join(warnings + gaps)
        raise PermissionError(
            "No tools remain after source-license/commercial policy enforcement: "
            + detail
        )

    rationale = (
        "ORBYTHRA Universal Deep Search selected the smallest authorized read-only "
        "tool set; factual lookups default to provider federation and can fan out "
        "across Turkish, English and domain-specific global sources."
    )
    if gaps:
        rationale += " Provider gaps: " + "; ".join(gaps)

    plan = InvestigationPlan(
        question_type=question_type,
        region=region,
        time_range=time_range,
        tools=allowed,
        rationale=rationale,
        max_tool_calls=min(settings.max_tool_calls, len(allowed)),
        commercial_warnings=warnings + gaps,
    )
    return plan, model_meta
