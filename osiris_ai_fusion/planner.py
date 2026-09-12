from __future__ import annotations

import json
import re
from typing import Any

from capabilities import (
    auto_tool_names,
    capability_specs,
    infer_capability_names,
    likely_requires_external_data,
    resolve_capability_gap,
)
from config import get_settings
from llm import ModelRouter
from osiris_client import READ_ONLY_TOOLS, normalize_tool_name
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
    "olağandışı", "anomali", "risk", "tehdit", "olay", "gelişme", "brief",
    "intelligence", "osint", "ülke", "bölge", "region", "threat", "incident",
}
DEFAULT_TOOL_SET = {"earthquakes", "fires", "weather", "gdelt", "news", "country_risk"}


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


def deterministic_tools(query: str, requested_tools: list[str] | None = None) -> list[str]:
    settings = get_settings()
    q = query.lower()
    available = auto_tool_names()

    native = {tool for keyword, tool in KEYWORD_TOOL_MAP.items() if keyword in q}
    capabilities = {name for name in infer_capability_names(query) if name in available}
    selected = native | capabilities

    if not selected and any(term in q for term in OSINT_BROAD_TERMS):
        selected = DEFAULT_TOOL_SET & available

    if not selected and likely_requires_external_data(query) and "web_search" in available:
        selected = {"web_search"}

    if not selected:
        selected = {"direct_reasoning"} if "direct_reasoning" in available else set()

    if requested_tools is not None:
        requested = {normalize_tool_name(tool) for tool in requested_tools}
        unknown = requested.difference(available)
        if unknown:
            raise PermissionError(f"Unknown, unavailable, or non-read-only tools requested: {sorted(unknown)}")
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
    region = scope.get("region")
    time_range = scope.get("time_range") or infer_time_range(query)
    question_type = infer_question_type(query)
    model_meta = {"provider": "deterministic", "model": "capability-router-v1"}

    if settings.ai_planner_enabled and requested_tools is None:
        system = (
            "You are OSIRIS Fusion's universal capability planner. Return only JSON matching the schema. "
            "Select only from AVAILABLE_TOOLS. Use the smallest sufficient set. Use direct_reasoning for "
            "drafting, rewriting, ideation and stable reasoning tasks. Use web_search for fresh public facts "
            "when it is available. Use specialized connectors such as sports_research when relevant. Never "
            "request active scanning, exploitation, credential access, facial tracking or intrusive surveillance."
        )
        prompt = (
            f"QUERY: {query}\n"
            f"USER_SCOPE: {json.dumps(scope, ensure_ascii=False)}\n"
            f"AVAILABLE_TOOLS: {', '.join(sorted(available))}\n"
            f"MAX_TOOL_CALLS: {settings.max_tool_calls}\n"
            "If a requested external capability is unavailable, do not invent a tool name."
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
                tools = valid[: settings.max_tool_calls]
                region = candidate.region or region
                time_range = candidate.time_range or time_range
                question_type = candidate.question_type
                model_meta = {"provider": model_result.provider, "model": model_result.model}
        except Exception:
            pass

    allowed, warnings = enforce_source_policy(tools)
    gaps = resolve_capability_gap(query, infer_capability_names(query))
    if tools and not allowed:
        detail = "; ".join(warnings + gaps)
        raise PermissionError(
            "No tools remain after source-license/commercial policy enforcement: " + detail
        )

    rationale = "Universal capability router selected the smallest authorized read-only tool set."
    if gaps:
        rationale += " Capability gaps: " + "; ".join(gaps)

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
