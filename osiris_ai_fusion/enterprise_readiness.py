from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from config import get_settings
from saas import AuthContext, require_identity

router = APIRouter(prefix="/enterprise", tags=["orbythra-enterprise-proof"])
Identity = Annotated[AuthContext, Depends(require_identity)]


class FingerprintRequest(BaseModel):
    query: str = Field(default="", max_length=4000)
    report: dict[str, Any] = Field(default_factory=dict)
    evidence_index: list[dict[str, Any]] = Field(default_factory=list, max_length=500)
    receipt: dict[str, Any] = Field(default_factory=dict)


class PilotCreate(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    use_case: str = Field(min_length=3, max_length=4000)
    owner: str = Field(default="", max_length=240)
    target_tasks: int = Field(default=25, ge=5, le=10000)


class PilotMetricUpdate(BaseModel):
    task_success_rate: float | None = Field(default=None, ge=0, le=1)
    grounded_claim_rate: float | None = Field(default=None, ge=0, le=1)
    human_acceptance_rate: float | None = Field(default=None, ge=0, le=1)
    median_latency_seconds: float | None = Field(default=None, ge=0)
    cost_per_task_usd: float | None = Field(default=None, ge=0)
    completed_tasks: int | None = Field(default=None, ge=0)
    notes: str = Field(default="", max_length=4000)


def _canonical(value: Any) -> Any:
    if isinstance(value, dict):
        volatile = {
            "request_id",
            "created_at",
            "updated_at",
            "latency_ms",
            "elapsed_ms",
            "timestamp",
        }
        return {
            str(key): _canonical(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in volatile
        }
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    if isinstance(value, float):
        return round(value, 8)
    return value


def knowledge_fingerprint(payload: FingerprintRequest | dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload, FingerprintRequest):
        raw = payload.model_dump()
    else:
        raw = dict(payload)
    canonical = _canonical(raw)
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    digest = hashlib.sha256(b"ORBYTHRA-KNOWLEDGE-FINGERPRINT-V1\x00" + encoded).hexdigest()
    evidence = raw.get("evidence_index") or []
    report = raw.get("report") or {}
    providers = sorted(
        {
            str(item.get("provider") or item.get("tool") or "unknown")
            for item in evidence
            if isinstance(item, dict)
        }
    )
    return {
        "version": "orbythra-knowledge-fingerprint-v1",
        "fingerprint": digest,
        "canonical_bytes": len(encoded),
        "evidence_count": len(evidence),
        "provider_families": providers,
        "claim_count": len(report.get("claims") or []) if isinstance(report, dict) else 0,
        "timeline_event_count": (
            len(report.get("historical_timeline") or []) if isinstance(report, dict) else 0
        ),
        "idea_count": len(report.get("developed_ideas") or []) if isinstance(report, dict) else 0,
        "purpose": (
            "Stable audit/deduplication identity for the evidence-report bundle; "
            "it is not a claim that the underlying answer is true."
        ),
    }


def product_readiness_scorecard() -> dict[str, Any]:
    dimensions = {
        "technical_architecture": {
            "score": 9.6,
            "evidence": [
                "multi-stage evidence-first graph",
                "provider federation",
                "world/science/engineering intelligence layers",
                "bounded adaptive cognition",
            ],
        },
        "productization": {
            "score": 9.3,
            "evidence": [
                "multi-tenant SaaS boundary",
                "health/readiness endpoints",
                "rate limiting and SLO metrics",
                "persistent goal operator",
                "production runbooks and buyer data-room automation",
            ],
        },
        "security_verification": {
            "score": 9.2,
            "evidence": [
                "intent sealing and replay protection",
                "evidence/report integrity receipts",
                "approval-gated side effects",
                "tenant isolation tests",
                "dependency and credential scans in CI",
            ],
        },
        "research_intelligence": {
            "score": 9.5,
            "evidence": [
                "historical timeline",
                "server-resolved spatial evidence",
                "cross-provider evidence normalization",
                "self-evaluation and bounded refinement",
                "testable idea development",
            ],
        },
        "memory_adaptation": {
            "score": 9.2,
            "evidence": [
                "tenant episodic memory",
                "consolidated evidence-linked fact memory",
                "memory-not-fresh-evidence rule",
                "evaluation-derived planning hints",
                "persistent multi-iteration goals",
            ],
        },
        "defensibility_moat": {
            "score": 9.1,
            "evidence": [
                "temporal-spatial evidence world model",
                "science/genome relationship graph",
                "proprietary world intelligence scoring",
                "knowledge fingerprint contract",
                "auditable autonomy and evidence lineage",
            ],
        },
        "commercial_readiness": {
            "score": 9.1,
            "evidence": [
                "pilot KPI ledger",
                "commercial metrics tooling",
                "procurement/privacy operations pack",
                "enterprise validation pack",
                "buyer data-room build pipeline",
            ],
        },
    }
    scores = [float(item["score"]) for item in dimensions.values()]
    return {
        "rubric": "internal engineering/product readiness; not a third-party valuation",
        "minimum_dimension_score": min(scores),
        "average_score": round(sum(scores) / len(scores), 2),
        "dimensions": dimensions,
        "external_proof": {
            "numeric_score": None,
            "status": "requires-real-world-evidence",
            "not_fabricated": True,
            "open_items": [
                "repeated live benchmark sample",
                "multi-week production SLO history",
                "independent pentest/evaluation",
                "real paid pilot/customer task-success and revenue evidence",
            ],
        },
    }


def moat_manifest() -> dict[str, Any]:
    return {
        "name": "ORBYTHRA Evidence-to-Decision Moat",
        "layers": [
            {
                "layer": "verifiable_research",
                "asset": "normalized evidence + source lineage + integrity receipts",
            },
            {
                "layer": "temporal_spatial_world_model",
                "asset": "entities/events bound to time, location, branch and evidence",
            },
            {
                "layer": "adaptive_operator",
                "asset": "memory + evaluation-derived policy + persistent bounded goals",
            },
            {
                "layer": "decision_intelligence",
                "asset": "world, engineering and science relationship scores with exposed inputs",
            },
            {
                "layer": "knowledge_fingerprint",
                "asset": "domain-separated stable identity for evidence/report bundles",
            },
        ],
        "claim_boundary": (
            "These are implementation differentiators. They do not by themselves prove a legal monopoly, "
            "patent position, market traction, or general AGI."
        ),
    }


class EnterpriseProofStore:
    def __init__(self, path: str | None = None) -> None:
        self.path = path or get_settings().store_path
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS enterprise_pilots (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    use_case TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    target_tasks INTEGER NOT NULL,
                    completed_tasks INTEGER NOT NULL DEFAULT 0,
                    task_success_rate REAL,
                    grounded_claim_rate REAL,
                    human_acceptance_rate REAL,
                    median_latency_seconds REAL,
                    cost_per_task_usd REAL,
                    notes TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_enterprise_pilots_workspace
                    ON enterprise_pilots(workspace_id, updated_at DESC);
                """
            )
            conn.commit()

    @staticmethod
    def _view(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        target = max(1, int(item["target_tasks"]))
        item["completion_ratio"] = round(min(1.0, int(item["completed_tasks"]) / target), 4)
        available = [
            float(item[key])
            for key in ("task_success_rate", "grounded_claim_rate", "human_acceptance_rate")
            if item.get(key) is not None
        ]
        item["quality_index"] = round(sum(available) / len(available), 4) if available else None
        item["evidence_status"] = (
            "self-reported-unverified"
            if item["completed_tasks"] > 0 and available
            else "awaiting-real-pilot-data"
        )
        item["evidence_note"] = (
            "Pilot metrics are user-entered; this ledger does not verify task records or customer sign-off."
        )
        return item

    def create(self, workspace_id: str, body: PilotCreate) -> dict[str, Any]:
        pilot_id = "pilot_" + uuid.uuid4().hex[:20]
        now = int(time.time())
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO enterprise_pilots "
                "(id, workspace_id, name, use_case, owner, target_tasks, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    pilot_id,
                    workspace_id,
                    body.name,
                    body.use_case,
                    body.owner,
                    body.target_tasks,
                    now,
                    now,
                ),
            )
            conn.commit()
        return self.get(workspace_id, pilot_id)

    def get(self, workspace_id: str, pilot_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM enterprise_pilots WHERE id=? AND workspace_id=?",
                (pilot_id, workspace_id),
            ).fetchone()
        if row is None:
            raise KeyError(pilot_id)
        return self._view(row)

    def list(self, workspace_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM enterprise_pilots WHERE workspace_id=? "
                "ORDER BY updated_at DESC LIMIT ?",
                (workspace_id, max(1, min(limit, 200))),
            ).fetchall()
        return [self._view(row) for row in rows]

    def update_metrics(
        self,
        workspace_id: str,
        pilot_id: str,
        body: PilotMetricUpdate,
    ) -> dict[str, Any]:
        current = self.get(workspace_id, pilot_id)
        updates = body.model_dump(exclude_none=True)
        updates["notes"] = body.notes if body.notes else current.get("notes", "")
        allowed = {
            "task_success_rate",
            "grounded_claim_rate",
            "human_acceptance_rate",
            "median_latency_seconds",
            "cost_per_task_usd",
            "completed_tasks",
            "notes",
        }
        merged = {key: current.get(key) for key in allowed}
        merged.update({key: value for key, value in updates.items() if key in allowed})
        now = int(time.time())
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE enterprise_pilots SET completed_tasks=?, task_success_rate=?, "
                "grounded_claim_rate=?, human_acceptance_rate=?, median_latency_seconds=?, "
                "cost_per_task_usd=?, notes=?, updated_at=? WHERE id=? AND workspace_id=?",
                (
                    int(merged.get("completed_tasks") or 0),
                    merged.get("task_success_rate"),
                    merged.get("grounded_claim_rate"),
                    merged.get("human_acceptance_rate"),
                    merged.get("median_latency_seconds"),
                    merged.get("cost_per_task_usd"),
                    str(merged.get("notes") or ""),
                    now,
                    pilot_id,
                    workspace_id,
                ),
            )
            conn.commit()
        if cursor.rowcount == 0:
            raise KeyError(pilot_id)
        return self.get(workspace_id, pilot_id)


proof_store = EnterpriseProofStore()


@router.get("/readiness")
async def enterprise_readiness(_: Identity) -> dict[str, Any]:
    return product_readiness_scorecard()


@router.get("/moat")
async def enterprise_moat(_: Identity) -> dict[str, Any]:
    return moat_manifest()


@router.post("/fingerprint")
async def enterprise_fingerprint(body: FingerprintRequest, _: Identity) -> dict[str, Any]:
    return knowledge_fingerprint(body)


@router.post("/pilots")
async def create_pilot(body: PilotCreate, auth: Identity) -> dict[str, Any]:
    return proof_store.create(auth.tenant_id, body)


@router.get("/pilots")
async def list_pilots(
    auth: Identity,
    limit: int = Query(default=100, ge=1, le=200),
) -> list[dict[str, Any]]:
    return proof_store.list(auth.tenant_id, limit=limit)


@router.post("/pilots/{pilot_id}/metrics")
async def update_pilot_metrics(
    pilot_id: str,
    body: PilotMetricUpdate,
    auth: Identity,
) -> dict[str, Any]:
    try:
        return proof_store.update_metrics(auth.tenant_id, pilot_id, body)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Pilot not found") from exc
