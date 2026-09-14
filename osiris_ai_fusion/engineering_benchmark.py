from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from engineering_intelligence import audit_engineering_answer


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def evaluate_answer(case: dict[str, Any], answer: str) -> dict[str, Any]:
    normalized = _norm(answer)
    audit = audit_engineering_answer(answer)
    required = [str(item) for item in case.get("required_topics") or []]
    topic_hits = {topic: _norm(topic) in normalized for topic in required}
    unknown_terms = [str(item) for item in case.get("unknowns") or []]
    unknown_mentions = sum(1 for term in unknown_terms if _norm(term) in normalized)
    topic_score = sum(topic_hits.values()) / len(topic_hits) if topic_hits else 1.0
    structure_score = sum(
        int(bool(audit.get(key)))
        for key in (
            "required_sections_complete",
            "four_modes_complete",
            "verification_complete",
        )
    ) / 3.0
    unknown_score = min(1.0, unknown_mentions / max(1, len(unknown_terms)))
    overall = 0.50 * structure_score + 0.35 * topic_score + 0.15 * unknown_score
    return {
        "case_id": case.get("id"),
        "structure_audit": audit,
        "topic_hits": topic_hits,
        "unknown_mentions": unknown_mentions,
        "unknown_count": len(unknown_terms),
        "scores": {
            "structure": round(structure_score, 4),
            "required_topics": round(topic_score, 4),
            "unknown_handling": round(unknown_score, 4),
            "overall": round(overall, 4),
        },
        "note": (
            "Automated benchmark scoring checks coverage/structure only. Independent engineers "
            "must validate physical correctness and safety."
        ),
    }


def load_cases(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path else Path(__file__).resolve().parent / "benchmarks" / "engineering_cases.json"
    return json.loads(target.read_text(encoding="utf-8"))
