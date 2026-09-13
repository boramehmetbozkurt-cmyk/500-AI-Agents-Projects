from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .models import Opportunity
from .risk import opportunity_source_risk


@dataclass(slots=True)
class OpportunitySpec:
    id: str
    name: str
    source_url: str
    chains: list[str]
    allowed_domains: list[str]
    eligibility_url_template: str | None = None
    estimated_value_usd: str | None = None
    notes: list[str] | None = None


def _validate_https(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError(f"Only absolute HTTPS URLs are allowed in opportunity manifests: {url}")


def load_registry(path: str | Path) -> list[OpportunitySpec]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Opportunity registry must be a JSON list")
    specs: list[OpportunitySpec] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Each opportunity must be a JSON object")
        source_url = str(item["source_url"])
        _validate_https(source_url)
        eligibility = item.get("eligibility_url_template")
        if eligibility is not None:
            eligibility = str(eligibility)
            _validate_https(eligibility.replace("{address}", "0x0000000000000000000000000000000000000000"))
        specs.append(
            OpportunitySpec(
                id=str(item["id"]),
                name=str(item["name"]),
                source_url=source_url,
                chains=[str(v) for v in item.get("chains", [])],
                allowed_domains=[str(v) for v in item.get("allowed_domains", [])],
                eligibility_url_template=eligibility,
                estimated_value_usd=str(item["estimated_value_usd"]) if item.get("estimated_value_usd") is not None else None,
                notes=[str(v) for v in item.get("notes", [])],
            )
        )
    return specs


def spec_to_opportunity(spec: OpportunitySpec, status: str, extra_notes: list[str] | None = None) -> Opportunity:
    from decimal import Decimal

    risk, warnings = opportunity_source_risk(spec.source_url, spec.allowed_domains)
    value = Decimal(spec.estimated_value_usd) if spec.estimated_value_usd is not None else None
    notes = list(spec.notes or []) + warnings + list(extra_notes or [])
    return Opportunity(
        id=spec.id,
        name=spec.name,
        source_url=spec.source_url,
        chains=spec.chains,
        status=status,
        estimated_value_usd=value,
        risk_score=risk,
        notes=notes,
        evidence=[spec.source_url],
    )
