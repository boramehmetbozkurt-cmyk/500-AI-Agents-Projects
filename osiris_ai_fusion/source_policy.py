from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from config import get_settings


@dataclass(frozen=True)
class SourcePolicy:
    tool: str
    provider: str
    status: str
    commercial_use: str
    attribution: str
    terms_url: str
    notes: str = ""


POLICIES: dict[str, SourcePolicy] = {
    "earthquakes": SourcePolicy(
        "earthquakes",
        "usgs",
        "public_domain",
        "allowed",
        "Credit USGS where practical.",
        "https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits",
    ),
    "fires": SourcePolicy(
        "fires",
        "nasa_firms",
        "open_public",
        "allowed_with_attribution",
        "Credit NASA FIRMS/LANCE and preserve source-specific notices.",
        "https://firms.modaps.eosdis.nasa.gov/",
        (
            "Basemap/third-party imagery can carry separate terms; fire detections "
            "and imagery are not interchangeable."
        ),
    ),
    "gdelt": SourcePolicy(
        "gdelt",
        "gdelt",
        "unrestricted_with_attribution",
        "allowed_with_attribution",
        "Cite GDELT Project and link to gdeltproject.org.",
        "https://www.gdeltproject.org/about.html",
    ),
    "cyber_threats": SourcePolicy(
        "cyber_threats",
        "nist_nvd_and_mixed",
        "mixed_review",
        "review",
        "Credit NIST/NVD for NVD-derived records; preserve third-party notices.",
        "https://www.nist.gov/copyrights-disclaimers",
    ),
    "malware": SourcePolicy(
        "malware",
        "nist_nvd_and_mixed",
        "mixed_review",
        "review",
        "Preserve source attribution and third-party notices.",
        "https://www.nist.gov/copyrights-disclaimers",
    ),
    "flights": SourcePolicy(
        "flights",
        "opensky",
        "license_required",
        "license_required",
        (
            "OpenSky attribution and a written commercial/operational license are "
            "required for product use."
        ),
        "https://opensky-network.org/about/terms-of-use",
    ),
    "calculator": SourcePolicy(
        "calculator",
        "local",
        "local_computation",
        "allowed",
        "No external source attribution required.",
        "local://calculator",
    ),
    "direct_reasoning": SourcePolicy(
        "direct_reasoning",
        "model_router",
        "model_output",
        "allowed",
        "Model-provider terms apply to the configured model endpoint.",
        "model://router",
        "Direct reasoning is not treated as fresh factual evidence.",
    ),
    "capability_gap": SourcePolicy(
        "capability_gap",
        "local",
        "local_system",
        "allowed",
        "No external source attribution required.",
        "local://capability-gap",
        (
            "Reports missing connector requirements and intentionally does not "
            "fabricate external facts."
        ),
    ),
    "web_search": SourcePolicy(
        "web_search",
        "configured_web_search",
        "connector_terms",
        "review",
        (
            "Preserve source URLs and attribution returned by the configured "
            "web-search connector."
        ),
        "connector://web_search",
        (
            "Commercial redistribution rights depend on the configured provider "
            "and underlying sources."
        ),
    ),
    "sports_research": SourcePolicy(
        "sports_research",
        "configured_sports",
        "connector_terms",
        "review",
        (
            "Preserve provider/source attribution returned by the configured "
            "sports connector."
        ),
        "connector://sports_research",
        "Sports data and odds feeds commonly require separate commercial rights.",
    ),
}

DEFAULT_REVIEW_POLICY = SourcePolicy(
    "*",
    "mixed_or_upstream",
    "mixed_review",
    "review",
    (
        "Preserve upstream attribution and verify provider terms before commercial "
        "redistribution."
    ),
    "https://www.osirisai.live/docs",
    (
        "OSIRIS aggregates multiple upstream sources; the OSIRIS MIT license does "
        "not override upstream data licenses."
    ),
)


def policy_for_tool(tool: str) -> SourcePolicy:
    if tool in POLICIES:
        return POLICIES[tool]
    fallback = asdict(DEFAULT_REVIEW_POLICY)
    fallback.pop("tool", None)
    return SourcePolicy(tool=tool, **fallback)


def policy_report(tools: Iterable[str] | None = None) -> list[dict[str, str]]:
    selected = sorted(set(tools or POLICIES))
    return [asdict(policy_for_tool(tool)) for tool in selected]


def enforce_source_policy(tools: Iterable[str]) -> tuple[list[str], list[str]]:
    settings = get_settings()
    licensed = settings.licensed_providers
    allowed: list[str] = []
    warnings: list[str] = []

    for tool in tools:
        policy = policy_for_tool(tool)
        if not settings.commercial_mode:
            allowed.append(tool)
            if policy.status in {
                "license_required",
                "mixed_review",
                "connector_terms",
            }:
                warnings.append(f"{tool}: {policy.status} — {policy.terms_url}")
            continue

        provider_tokens = {
            part.strip()
            for part in policy.provider.split("_and_")
            if part.strip()
        }
        explicitly_licensed = bool(provider_tokens & licensed) or policy.provider in licensed
        if policy.commercial_use == "license_required" and not explicitly_licensed:
            warnings.append(
                f"BLOCKED {tool}: commercial license required from {policy.provider}"
            )
            continue
        if (
            policy.commercial_use == "review"
            and settings.strict_commercial_sources
            and not explicitly_licensed
        ):
            warnings.append(
                f"BLOCKED {tool}: commercial source terms require review "
                f"({policy.provider})"
            )
            continue
        allowed.append(tool)
        if policy.commercial_use != "allowed":
            warnings.append(
                f"{tool}: {policy.commercial_use} — {policy.attribution}"
            )

    return allowed, warnings
