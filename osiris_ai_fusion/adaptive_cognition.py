from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from config import get_settings

_WORD_RE = re.compile(r"[\wçğıöşüÇĞİÖŞÜ-]+", re.UNICODE)


def _tokens(text: str) -> set[str]:
    return {item.lower() for item in _WORD_RE.findall(text) if len(item) > 2}


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _asks_history(query: str) -> bool:
    q = query.lower()
    return any(term in q for term in ("tarih", "history", "timeline", "geçmiş", "evolution", "gelişim"))


def _asks_spatial(query: str) -> bool:
    q = query.lower()
    return any(term in q for term in ("nerede", "where", "harita", "map", "konum", "location", "şehir", "city", "ülke", "country"))


def _asks_ideas(query: str) -> bool:
    q = query.lower()
    return any(term in q for term in ("fikir", "idea", "öner", "develop", "geliştir", "concept", "strateji", "strategy"))


class CognitiveMemory:
    """Tenant-isolated episodic memory and evaluation ledger.

    This is deliberately retrieval-only during planning: memories can influence
    prioritisation and continuity, but they are not treated as fresh factual evidence.
    """

    def __init__(self, path: str | None = None) -> None:
        self.path = path or get_settings().store_path
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS cognitive_memories (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    query TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    topics_json TEXT NOT NULL,
                    quality_score REAL NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_cognitive_memories_workspace
                    ON cognitive_memories(workspace_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS cognitive_evaluations (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    query TEXT NOT NULL,
                    score REAL NOT NULL,
                    evaluation_json TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_cognitive_eval_workspace
                    ON cognitive_evaluations(workspace_id, created_at DESC);
                """
            )
            conn.commit()

    def recall(self, query: str, workspace_id: str, limit: int = 5) -> list[dict[str, Any]]:
        query_tokens = _tokens(query)
        if not query_tokens:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, query, summary, topics_json, quality_score, created_at "
                "FROM cognitive_memories WHERE workspace_id=? "
                "ORDER BY created_at DESC LIMIT 200",
                (workspace_id,),
            ).fetchall()
        ranked: list[tuple[float, dict[str, Any]]] = []
        now = int(time.time())
        for row in rows:
            item = dict(row)
            memory_tokens = _tokens(str(item["query"]) + " " + str(item["summary"]))
            union = query_tokens | memory_tokens
            overlap = len(query_tokens & memory_tokens) / max(1, len(union))
            age_days = max(0.0, (now - int(item["created_at"])) / 86400.0)
            recency = 1.0 / (1.0 + age_days / 30.0)
            quality = _clamp(float(item["quality_score"]))
            score = 0.72 * overlap + 0.18 * quality + 0.10 * recency
            if overlap >= 0.06:
                item["relevance"] = round(score, 4)
                item["topics"] = json.loads(item.pop("topics_json") or "[]")
                ranked.append((score, item))
        ranked.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in ranked[: max(1, min(limit, 10))]]

    def remember(
        self,
        query: str,
        report: dict[str, Any],
        evaluation: dict[str, Any],
        workspace_id: str,
    ) -> str:
        memory_id = "mem_" + uuid.uuid4().hex[:20]
        claims = [str(row.get("text") or "") for row in report.get("claims", [])[:5] if isinstance(row, dict)]
        ideas = [str(row.get("title") or "") for row in report.get("developed_ideas", [])[:4] if isinstance(row, dict)]
        timeline = [str(row.get("title") or "") for row in report.get("historical_timeline", [])[:5] if isinstance(row, dict)]
        parts = [str(report.get("bluf") or ""), *claims, *timeline, *ideas]
        summary = " | ".join(part.strip() for part in parts if part.strip())[:6000]
        topics = sorted(_tokens(query + " " + summary))[:80]
        quality = _clamp(float(evaluation.get("score", 0.0)))
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO cognitive_memories VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    memory_id,
                    workspace_id,
                    query,
                    summary,
                    json.dumps(topics, ensure_ascii=False),
                    quality,
                    int(time.time()),
                ),
            )
            conn.commit()
        return memory_id

    def record_evaluation(self, query: str, evaluation: dict[str, Any], workspace_id: str) -> str:
        evaluation_id = "eval_" + uuid.uuid4().hex[:20]
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO cognitive_evaluations VALUES (?, ?, ?, ?, ?, ?)",
                (
                    evaluation_id,
                    workspace_id,
                    query,
                    _clamp(float(evaluation.get("score", 0.0))),
                    json.dumps(evaluation, ensure_ascii=False, separators=(",", ":"), default=str),
                    int(time.time()),
                ),
            )
            conn.commit()
        return evaluation_id


def build_cognitive_plan(query: str, memories: list[dict[str, Any]]) -> dict[str, Any]:
    q = query.strip()
    q_lower = q.lower()
    complexity = 1
    if len(_tokens(q)) > 12:
        complexity += 1
    if any(term in q_lower for term in ("karşılaştır", "compare", "analiz", "analyze", "neden", "why")):
        complexity += 1
    if _asks_history(q) or _asks_spatial(q):
        complexity += 1
    if _asks_ideas(q):
        complexity += 1
    complexity = min(complexity, 5)

    chunks = re.split(r"[?;]|\b(?:ve|and|then|sonra|ayrıca|also)\b", q, flags=re.IGNORECASE)
    objectives = [chunk.strip(" ,.-") for chunk in chunks if len(chunk.strip(" ,.-")) >= 5]
    if not objectives:
        objectives = [q]
    objectives = list(dict.fromkeys(objectives))[:6]

    criteria = [
        "Answer the user's actual question directly.",
        "Bind factual/current claims to retrieved evidence and expose uncertainty.",
        "Do not treat remembered conclusions as fresh evidence.",
    ]
    if _asks_history(q):
        criteria.append("Produce an evidence-linked chronological history/timeline.")
    if _asks_spatial(q):
        criteria.append("Resolve supported locations to server-verified digital-map markers.")
    if _asks_ideas(q):
        criteria.append("Develop testable ideas with rationale, risks, confidence and next experiment.")

    return {
        "complexity": complexity,
        "objectives": objectives,
        "success_criteria": criteria,
        "memory_hits": len(memories),
        "adaptation_policy": {
            "max_refinement_passes": 1,
            "new_external_tool_calls_during_refinement": 0,
            "active_actions": "denied",
        },
    }


def evaluate_report(
    query: str,
    report: dict[str, Any],
    evidence_items: list[dict[str, Any]],
) -> dict[str, Any]:
    claims = [row for row in report.get("claims", []) if isinstance(row, dict)]
    cited_claims = [row for row in claims if row.get("evidence_ids")]
    evidence_coverage = len(cited_claims) / max(1, len(claims)) if claims else (1.0 if evidence_items else 0.35)

    domains = {str(row.get("domain") or "") for row in evidence_items if row.get("domain")}
    providers = {
        str(provider)
        for row in evidence_items
        for provider in (row.get("providers") or [])
        if provider
    }
    source_diversity = _clamp((len(domains) + len(providers)) / 6.0)

    bluf = str(report.get("bluf") or "").strip()
    completeness = _clamp(len(bluf) / 500.0)
    if report.get("data_gaps"):
        completeness = min(1.0, completeness + 0.08)

    timeline = [row for row in report.get("historical_timeline", []) if isinstance(row, dict)]
    timeline_quality = 1.0
    if _asks_history(query):
        timeline_quality = _clamp(sum(1 for row in timeline if row.get("date") and row.get("evidence_ids")) / 4.0)

    markers = [row for row in report.get("map_markers", []) if isinstance(row, dict)]
    spatial_quality = 1.0 if not _asks_spatial(query) else _clamp(len(markers) / 3.0)

    ideas = [row for row in report.get("developed_ideas", []) if isinstance(row, dict)]
    idea_quality = 1.0
    if _asks_ideas(query):
        good = sum(1 for row in ideas if row.get("thesis") and row.get("next_experiment") and row.get("risks") is not None)
        idea_quality = _clamp(good / 3.0)

    confidence = _clamp(float(report.get("overall_confidence", 0.0)))
    evidence_strength = _clamp(len(evidence_items) / 8.0)
    calibration = 1.0 - abs(confidence - evidence_strength) * 0.7
    calibration = _clamp(calibration)

    metrics = {
        "evidence_coverage": round(evidence_coverage, 4),
        "source_diversity": round(source_diversity, 4),
        "answer_completeness": round(completeness, 4),
        "timeline_quality": round(timeline_quality, 4),
        "spatial_quality": round(spatial_quality, 4),
        "idea_quality": round(idea_quality, 4),
        "confidence_calibration": round(calibration, 4),
    }
    weights = {
        "evidence_coverage": 0.26,
        "source_diversity": 0.14,
        "answer_completeness": 0.18,
        "timeline_quality": 0.12,
        "spatial_quality": 0.10,
        "idea_quality": 0.10,
        "confidence_calibration": 0.10,
    }
    score = sum(metrics[key] * weight for key, weight in weights.items())
    issues: list[str] = []
    if metrics["evidence_coverage"] < 0.65:
        issues.append("Too many factual claims lack evidence bindings.")
    if metrics["source_diversity"] < 0.35 and len(evidence_items) > 1:
        issues.append("Evidence is concentrated in too few source/provider families.")
    if metrics["answer_completeness"] < 0.55:
        issues.append("The direct answer is underdeveloped.")
    if metrics["timeline_quality"] < 0.6:
        issues.append("Requested historical timeline is incomplete or weakly evidenced.")
    if metrics["spatial_quality"] < 0.6:
        issues.append("Requested spatial context is not sufficiently resolved.")
    if metrics["idea_quality"] < 0.6:
        issues.append("Requested ideas are not yet testable enough.")

    return {
        "score": round(_clamp(score), 4),
        "metrics": metrics,
        "issues": issues,
        "refinement_required": bool(score < 0.74 or issues),
        "threshold": 0.74,
        "policy": "bounded-reflection-no-new-tools",
    }


def refinement_directives(evaluation: dict[str, Any]) -> list[str]:
    directives = [
        "Keep every supported fact evidence-bound and remove unsupported factual overreach.",
        "Preserve server-resolved map markers and visual assets exactly; do not invent replacements.",
        "Keep uncertainty explicit and answer the user in the user's language.",
    ]
    directives.extend(str(item) for item in evaluation.get("issues", [])[:8])
    return directives
