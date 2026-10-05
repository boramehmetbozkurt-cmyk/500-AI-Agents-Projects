from __future__ import annotations

import re

from app.models import PlanRequest, PlanResponse

_WORD_RE = re.compile(r"[\wçğıöşüÇĞİÖŞÜ-]+", re.UNICODE)


def _tokens(text: str) -> set[str]:
    return {item.lower() for item in _WORD_RE.findall(text) if len(item) > 2}


def build_plan(request: PlanRequest) -> PlanResponse:
    query = request.query.strip()
    q = query.lower()
    complexity = 1
    if len(_tokens(query)) > 12:
        complexity += 1
    if any(term in q for term in ("karşılaştır", "compare", "analiz", "analyze", "neden", "why")):
        complexity += 1
    if any(term in q for term in ("tarih", "history", "timeline", "geçmiş", "evolution")):
        complexity += 1
    if any(term in q for term in ("nerede", "where", "harita", "map", "konum", "location")):
        complexity += 1
    if any(term in q for term in ("fikir", "idea", "öner", "develop", "geliştir", "strategy", "strateji")):
        complexity += 1
    complexity = min(complexity, 5)

    chunks = re.split(r"[?;]|\b(?:ve|and|then|sonra|ayrıca|also)\b", query, flags=re.IGNORECASE)
    objectives = [chunk.strip(" ,.-") for chunk in chunks if len(chunk.strip(" ,.-")) >= 5]
    if not objectives:
        objectives = [query]
    objectives = list(dict.fromkeys(objectives))[:6]

    criteria = [
        "Answer the actual question directly.",
        "Bind factual claims to explicit evidence IDs.",
        "Separate assumptions, unknowns and verified facts.",
        "Abstain or qualify when evidence does not pass the gate.",
        "Expose verification steps so the result can be reproduced.",
    ]

    modes = ["evidence", "reasoning", "verification"]
    if any(term in q for term in ("mühendis", "engineering", "teknik", "design", "tasarım")):
        modes.append("engineering_intelligence")
    if any(term in q for term in ("tarih", "history", "timeline", "geçmiş")):
        modes.append("temporal")
    if any(term in q for term in ("harita", "map", "konum", "location")):
        modes.append("spatial")

    return PlanResponse(
        complexity=complexity,
        objectives=objectives,
        success_criteria=criteria,
        modes=modes,
        requires_fresh_evidence=True,
    )
