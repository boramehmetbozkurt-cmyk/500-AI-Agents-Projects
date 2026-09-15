from __future__ import annotations

import json
import math
import sqlite3
import threading
import time
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from config import get_settings
from saas import AuthContext, require_identity

REALITY_BRANCH = "reality"
StatementKind = Literal["claim", "fact", "belief", "assumption"]


class WorldEventCreate(BaseModel):
    entity_id: str = Field(min_length=1, max_length=200)
    entity_type: str = Field(min_length=1, max_length=120)
    entity_label: str = Field(default="", max_length=240)
    predicate: str = Field(min_length=1, max_length=160)
    value: Any
    statement_kind: StatementKind = "claim"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list, max_length=32)
    source_ids: list[str] = Field(default_factory=list, max_length=32)
    valid_from: int | None = None
    valid_to: int | None = None
    branch_id: str = Field(default=REALITY_BRANCH, min_length=1, max_length=100)
    object_entity_id: str | None = Field(default=None, max_length=200)
    object_entity_type: str | None = Field(default=None, max_length=120)
    object_entity_label: str | None = Field(default=None, max_length=240)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_semantics(self) -> WorldEventCreate:
        if self.statement_kind == "fact" and not self.evidence_ids:
            raise ValueError("Facts require at least one evidence_id")
        if self.statement_kind == "assumption" and self.branch_id == REALITY_BRANCH:
            raise ValueError("Assumptions are only allowed on fork branches")
        if self.statement_kind == "fact" and self.branch_id != REALITY_BRANCH:
            raise ValueError("Fork branches cannot assert new facts; use assumption, claim or belief")
        if self.valid_to is not None and self.valid_from is not None:
            if self.valid_to <= self.valid_from:
                raise ValueError("valid_to must be greater than valid_from")
        return self


class WorldBatchCreate(BaseModel):
    events: list[WorldEventCreate] = Field(min_length=1, max_length=100)


class WorldForkCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    hypothesis: str = Field(min_length=1, max_length=1200)
    parent_branch_id: str = Field(default=REALITY_BRANCH, min_length=1, max_length=100)
    fork_observed_at: int | None = None


class WorldStore:
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
                CREATE TABLE IF NOT EXISTS world_entities (
                    workspace_id TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    label TEXT NOT NULL,
                    first_seen_at INTEGER NOT NULL,
                    last_seen_at INTEGER NOT NULL,
                    PRIMARY KEY(workspace_id, entity_id)
                );

                CREATE TABLE IF NOT EXISTS world_branches (
                    id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    hypothesis TEXT NOT NULL,
                    parent_branch_id TEXT NOT NULL,
                    fork_observed_at INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY(workspace_id, id)
                );

                CREATE TABLE IF NOT EXISTS world_events (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    branch_id TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_label TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    statement_kind TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    evidence_ids_json TEXT NOT NULL,
                    source_ids_json TEXT NOT NULL,
                    observed_at INTEGER NOT NULL,
                    valid_from INTEGER NOT NULL,
                    valid_to INTEGER,
                    object_entity_id TEXT,
                    object_entity_type TEXT,
                    object_entity_label TEXT,
                    metadata_json TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_world_events_scope
                    ON world_events(workspace_id, branch_id, observed_at);
                CREATE INDEX IF NOT EXISTS idx_world_events_entity
                    ON world_events(workspace_id, entity_id, predicate, observed_at);
                CREATE INDEX IF NOT EXISTS idx_world_events_validity
                    ON world_events(workspace_id, valid_from, valid_to);
                CREATE INDEX IF NOT EXISTS idx_world_branches_workspace
                    ON world_branches(workspace_id, created_at DESC);
                """
            )
            conn.commit()

    @staticmethod
    def _id(prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:20]}"

    def _branch_exists(self, workspace_id: str, branch_id: str) -> bool:
        if branch_id == REALITY_BRANCH:
            return True
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM world_branches WHERE workspace_id=? AND id=?",
                (workspace_id, branch_id),
            ).fetchone()
        return row is not None

    def _upsert_entity(
        self,
        conn: sqlite3.Connection,
        *,
        workspace_id: str,
        entity_id: str,
        entity_type: str,
        label: str,
        now: int,
    ) -> None:
        clean_label = label.strip() or entity_id
        conn.execute(
            """
            INSERT INTO world_entities(
                workspace_id, entity_id, entity_type, label, first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(workspace_id, entity_id) DO UPDATE SET
                entity_type=excluded.entity_type,
                label=CASE WHEN excluded.label != excluded.entity_id
                    THEN excluded.label ELSE world_entities.label END,
                last_seen_at=excluded.last_seen_at
            """,
            (workspace_id, entity_id, entity_type, clean_label, now, now),
        )

    def append_event(
        self,
        workspace_id: str,
        event: WorldEventCreate,
        *,
        observed_at: int | None = None,
    ) -> dict[str, Any]:
        if not self._branch_exists(workspace_id, event.branch_id):
            raise KeyError(f"Unknown world branch: {event.branch_id}")

        now = int(time.time())
        observed = now if observed_at is None else int(observed_at)
        valid_from = observed if event.valid_from is None else int(event.valid_from)
        event_id = self._id("wev")
        payload = event.model_dump()
        value_json = json.dumps(payload["value"], ensure_ascii=False, separators=(",", ":"), default=str)
        metadata_json = json.dumps(
            payload["metadata"], ensure_ascii=False, separators=(",", ":"), default=str
        )
        evidence_json = json.dumps(payload["evidence_ids"], ensure_ascii=False, separators=(",", ":"))
        source_json = json.dumps(payload["source_ids"], ensure_ascii=False, separators=(",", ":"))

        with self._lock, self._connect() as conn:
            self._upsert_entity(
                conn,
                workspace_id=workspace_id,
                entity_id=event.entity_id,
                entity_type=event.entity_type,
                label=event.entity_label,
                now=now,
            )
            if event.object_entity_id:
                self._upsert_entity(
                    conn,
                    workspace_id=workspace_id,
                    entity_id=event.object_entity_id,
                    entity_type=event.object_entity_type or "unknown",
                    label=event.object_entity_label or event.object_entity_id,
                    now=now,
                )
            conn.execute(
                """
                INSERT INTO world_events(
                    id, workspace_id, branch_id, entity_id, entity_type, entity_label,
                    predicate, value_json, statement_kind, confidence, evidence_ids_json,
                    source_ids_json, observed_at, valid_from, valid_to, object_entity_id,
                    object_entity_type, object_entity_label, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    workspace_id,
                    event.branch_id,
                    event.entity_id,
                    event.entity_type,
                    event.entity_label.strip() or event.entity_id,
                    event.predicate,
                    value_json,
                    event.statement_kind,
                    event.confidence,
                    evidence_json,
                    source_json,
                    observed,
                    valid_from,
                    event.valid_to,
                    event.object_entity_id,
                    event.object_entity_type,
                    event.object_entity_label,
                    metadata_json,
                    now,
                ),
            )
            conn.commit()
        return self.get_event(workspace_id, event_id)

    def append_batch(
        self,
        workspace_id: str,
        events: list[WorldEventCreate],
        *,
        observed_at: int | None = None,
    ) -> list[dict[str, Any]]:
        return [
            self.append_event(workspace_id, event, observed_at=observed_at)
            for event in events
        ]

    def get_event(self, workspace_id: str, event_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM world_events WHERE workspace_id=? AND id=?",
                (workspace_id, event_id),
            ).fetchone()
        if row is None:
            raise KeyError(event_id)
        return self._decode_event(row)

    @staticmethod
    def _decode_event(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        item = dict(row)
        item["value"] = json.loads(item.pop("value_json"))
        item["evidence_ids"] = json.loads(item.pop("evidence_ids_json"))
        item["source_ids"] = json.loads(item.pop("source_ids_json"))
        item["metadata"] = json.loads(item.pop("metadata_json"))
        return item

    def create_fork(
        self,
        workspace_id: str,
        request: WorldForkCreate,
    ) -> dict[str, Any]:
        if not self._branch_exists(workspace_id, request.parent_branch_id):
            raise KeyError(f"Unknown parent branch: {request.parent_branch_id}")
        now = int(time.time())
        fork_at = now if request.fork_observed_at is None else int(request.fork_observed_at)
        if fork_at > now:
            raise ValueError("fork_observed_at cannot be in the future")
        branch_id = self._id("fork")
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO world_branches(
                    id, workspace_id, name, hypothesis, parent_branch_id,
                    fork_observed_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    branch_id,
                    workspace_id,
                    request.name,
                    request.hypothesis,
                    request.parent_branch_id,
                    fork_at,
                    now,
                ),
            )
            conn.commit()
        return self.get_branch(workspace_id, branch_id)

    def get_branch(self, workspace_id: str, branch_id: str) -> dict[str, Any]:
        if branch_id == REALITY_BRANCH:
            return {
                "id": REALITY_BRANCH,
                "workspace_id": workspace_id,
                "name": "Reality",
                "hypothesis": "Observed reality branch",
                "parent_branch_id": "",
                "fork_observed_at": None,
                "created_at": None,
            }
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM world_branches WHERE workspace_id=? AND id=?",
                (workspace_id, branch_id),
            ).fetchone()
        if row is None:
            raise KeyError(branch_id)
        return dict(row)

    def list_branches(self, workspace_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM world_branches
                WHERE workspace_id=?
                ORDER BY created_at DESC
                """,
                (workspace_id,),
            ).fetchall()
        return [self.get_branch(workspace_id, REALITY_BRANCH), *[dict(row) for row in rows]]

    def _lineage(
        self,
        workspace_id: str,
        branch_id: str,
        observed_at: int,
    ) -> list[tuple[str, int]]:
        if branch_id == REALITY_BRANCH:
            return [(REALITY_BRANCH, observed_at)]
        branch = self.get_branch(workspace_id, branch_id)
        fork_at = int(branch["fork_observed_at"])
        parent_cap = min(observed_at, fork_at)
        return [
            *self._lineage(workspace_id, str(branch["parent_branch_id"]), parent_cap),
            (branch_id, observed_at),
        ]

    def _events_for_snapshot(
        self,
        workspace_id: str,
        branch_id: str,
        observed_at: int,
        valid_at: int,
        entity_id: str | None,
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        with self._connect() as conn:
            for lineage_branch, cap in self._lineage(workspace_id, branch_id, observed_at):
                sql = """
                    SELECT * FROM world_events
                    WHERE workspace_id=? AND branch_id=?
                      AND observed_at<=?
                      AND valid_from<=?
                      AND (valid_to IS NULL OR valid_to>?)
                """
                params: list[Any] = [
                    workspace_id,
                    lineage_branch,
                    cap,
                    valid_at,
                    valid_at,
                ]
                if entity_id:
                    sql += " AND entity_id=?"
                    params.append(entity_id)
                sql += " ORDER BY observed_at ASC, created_at ASC, id ASC"
                rows = conn.execute(sql, params).fetchall()
                events.extend(self._decode_event(row) for row in rows)
        return events

    @staticmethod
    def _event_view(event: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": event["id"],
            "branch_id": event["branch_id"],
            "statement_kind": event["statement_kind"],
            "value": event["value"],
            "confidence": event["confidence"],
            "evidence_ids": event["evidence_ids"],
            "source_ids": event["source_ids"],
            "observed_at": event["observed_at"],
            "valid_from": event["valid_from"],
            "valid_to": event["valid_to"],
            "object_entity_id": event.get("object_entity_id"),
            "metadata": event["metadata"],
        }

    @staticmethod
    def _value_key(value: Any) -> str:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)

    def snapshot(
        self,
        workspace_id: str,
        *,
        branch_id: str = REALITY_BRANCH,
        observed_at: int | None = None,
        valid_at: int | None = None,
        entity_id: str | None = None,
    ) -> dict[str, Any]:
        if not self._branch_exists(workspace_id, branch_id):
            raise KeyError(branch_id)
        now = int(time.time())
        observed = now if observed_at is None else int(observed_at)
        valid = observed if valid_at is None else int(valid_at)
        events = self._events_for_snapshot(
            workspace_id,
            branch_id,
            observed,
            valid,
            entity_id,
        )
        groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for event in events:
            groups[(str(event["entity_id"]), str(event["predicate"]))].append(event)

        states: list[dict[str, Any]] = []
        for (subject_id, predicate), rows in sorted(groups.items()):
            facts = [row for row in rows if row["statement_kind"] == "fact"]
            claims = [row for row in rows if row["statement_kind"] == "claim"]
            beliefs = [row for row in rows if row["statement_kind"] == "belief"]
            assumptions = [row for row in rows if row["statement_kind"] == "assumption"]

            fact = facts[-1] if facts else None
            belief = beliefs[-1] if beliefs else None
            assumption = assumptions[-1] if assumptions else None
            recent_claims = list(reversed(claims[-8:]))

            if assumption is not None:
                effective = assumption
                truth_status = "hypothetical"
            elif fact is not None:
                effective = fact
                fact_key = self._value_key(fact["value"])
                disputed = any(self._value_key(claim["value"]) != fact_key for claim in claims)
                truth_status = "verified_disputed" if disputed else "verified"
            elif claims:
                effective = max(
                    claims,
                    key=lambda item: (
                        float(item["confidence"]),
                        int(item["observed_at"]),
                        int(item["created_at"]),
                    ),
                )
                distinct_claims = {self._value_key(claim["value"]) for claim in claims}
                truth_status = "contested" if len(distinct_claims) > 1 else "claimed"
            elif belief is not None:
                effective = belief
                truth_status = "belief_only"
            else:
                continue

            states.append(
                {
                    "entity_id": subject_id,
                    "entity_type": rows[-1]["entity_type"],
                    "entity_label": rows[-1]["entity_label"],
                    "predicate": predicate,
                    "truth_status": truth_status,
                    "effective": self._event_view(effective),
                    "fact": self._event_view(fact) if fact else None,
                    "claims": [self._event_view(claim) for claim in recent_claims],
                    "belief": self._event_view(belief) if belief else None,
                    "assumption": self._event_view(assumption) if assumption else None,
                }
            )

        return {
            "workspace_id": workspace_id,
            "branch_id": branch_id,
            "observed_at": observed,
            "valid_at": valid,
            "state_count": len(states),
            "states": states,
        }

    def diff(
        self,
        workspace_id: str,
        *,
        left_branch_id: str,
        right_branch_id: str,
        observed_at: int | None = None,
        valid_at: int | None = None,
    ) -> dict[str, Any]:
        left = self.snapshot(
            workspace_id,
            branch_id=left_branch_id,
            observed_at=observed_at,
            valid_at=valid_at,
        )
        right = self.snapshot(
            workspace_id,
            branch_id=right_branch_id,
            observed_at=observed_at,
            valid_at=valid_at,
        )

        def index(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
            return {
                f"{item['entity_id']}::{item['predicate']}": item
                for item in snapshot["states"]
            }

        left_index = index(left)
        right_index = index(right)
        changes: list[dict[str, Any]] = []
        for key in sorted(set(left_index) | set(right_index)):
            before = left_index.get(key)
            after = right_index.get(key)
            before_key = (
                None
                if before is None
                else (
                    self._value_key(before["effective"]["value"]),
                    before["truth_status"],
                )
            )
            after_key = (
                None
                if after is None
                else (
                    self._value_key(after["effective"]["value"]),
                    after["truth_status"],
                )
            )
            if before_key != after_key:
                changes.append({"key": key, "before": before, "after": after})

        return {
            "workspace_id": workspace_id,
            "left_branch_id": left_branch_id,
            "right_branch_id": right_branch_id,
            "observed_at": left["observed_at"],
            "valid_at": left["valid_at"],
            "change_count": len(changes),
            "changes": changes,
        }

    def graph(
        self,
        workspace_id: str,
        *,
        branch_id: str = REALITY_BRANCH,
        observed_at: int | None = None,
        valid_at: int | None = None,
        limit: int = 500,
    ) -> dict[str, Any]:
        state = self.snapshot(
            workspace_id,
            branch_id=branch_id,
            observed_at=observed_at,
            valid_at=valid_at,
        )
        state["states"] = state["states"][:limit]
        node_ids: set[str] = set()
        edges: list[dict[str, Any]] = []
        for item in state["states"]:
            node_ids.add(item["entity_id"])
            effective = item["effective"]
            target = effective.get("object_entity_id")
            if target:
                node_ids.add(str(target))
                edges.append(
                    {
                        "source": item["entity_id"],
                        "target": target,
                        "predicate": item["predicate"],
                        "truth_status": item["truth_status"],
                        "confidence": effective["confidence"],
                        "event_id": effective["id"],
                    }
                )

        nodes: list[dict[str, Any]] = []
        if node_ids:
            placeholders = ",".join("?" for _ in node_ids)
            params: list[Any] = [workspace_id, *sorted(node_ids)]
            with self._connect() as conn:
                rows = conn.execute(
                    f"""
                    SELECT entity_id, entity_type, label, first_seen_at, last_seen_at
                    FROM world_entities
                    WHERE workspace_id=? AND entity_id IN ({placeholders})
                    ORDER BY entity_id
                    """,
                    params,
                ).fetchall()
            nodes = [dict(row) for row in rows]

        return {
            "workspace_id": workspace_id,
            "branch_id": branch_id,
            "observed_at": state["observed_at"],
            "valid_at": state["valid_at"],
            "nodes": nodes,
            "edges": edges,
        }

    def pulse(
        self,
        workspace_id: str,
        *,
        window_seconds: int = 3600,
        now: int | None = None,
    ) -> dict[str, Any]:
        current_time = int(time.time()) if now is None else int(now)
        current_start = current_time - window_seconds
        previous_start = current_start - window_seconds
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT entity_type, observed_at
                FROM world_events
                WHERE workspace_id=? AND branch_id=?
                  AND observed_at>? AND observed_at<=?
                """,
                (workspace_id, REALITY_BRANCH, previous_start, current_time),
            ).fetchall()

        current: dict[str, int] = defaultdict(int)
        previous: dict[str, int] = defaultdict(int)
        for row in rows:
            if int(row["observed_at"]) > current_start:
                current[str(row["entity_type"])] += 1
            else:
                previous[str(row["entity_type"])] += 1

        categories: list[dict[str, Any]] = []
        for entity_type in sorted(set(current) | set(previous)):
            current_count = current[entity_type]
            previous_count = previous[entity_type]
            delta = current_count - previous_count
            change_score = delta / math.sqrt(previous_count + 1)
            categories.append(
                {
                    "entity_type": entity_type,
                    "current_count": current_count,
                    "previous_count": previous_count,
                    "delta": delta,
                    "change_score": round(change_score, 3),
                    "unusual": abs(change_score) >= 2.0,
                }
            )
        categories.sort(key=lambda item: abs(float(item["change_score"])), reverse=True)
        return {
            "workspace_id": workspace_id,
            "window_seconds": window_seconds,
            "as_of": current_time,
            "unusual": any(bool(item["unusual"]) for item in categories),
            "categories": categories,
        }


settings = get_settings()
world_store = WorldStore(settings.store_path)
router = APIRouter(prefix="/world", tags=["world"])
Identity = Annotated[AuthContext, Depends(require_identity)]


@router.get("")
async def world_info(auth: Identity) -> dict[str, Any]:
    return {
        "name": "OSIRIS World",
        "mode": "verified-living-world-model",
        "workspace_id": auth.tenant_id,
        "reality_branch": REALITY_BRANCH,
        "principles": [
            "claim_fact_belief_separation",
            "bitemporal_world_state",
            "evidence_required_for_facts",
            "forked_counterfactual_worlds",
            "tenant_isolation",
        ],
    }


@router.post("/events")
async def create_world_event(body: WorldEventCreate, auth: Identity) -> dict[str, Any]:
    try:
        return world_store.append_event(auth.tenant_id, body)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/events/batch")
async def create_world_events(body: WorldBatchCreate, auth: Identity) -> dict[str, Any]:
    try:
        events = world_store.append_batch(auth.tenant_id, body.events)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"count": len(events), "events": events}


@router.get("/state")
async def world_state(
    auth: Identity,
    branch_id: str = Query(default=REALITY_BRANCH, max_length=100),
    observed_at: int | None = Query(default=None, ge=0),
    valid_at: int | None = Query(default=None, ge=0),
    entity_id: str | None = Query(default=None, max_length=200),
) -> dict[str, Any]:
    try:
        return world_store.snapshot(
            auth.tenant_id,
            branch_id=branch_id,
            observed_at=observed_at,
            valid_at=valid_at,
            entity_id=entity_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/graph")
async def world_graph(
    auth: Identity,
    branch_id: str = Query(default=REALITY_BRANCH, max_length=100),
    observed_at: int | None = Query(default=None, ge=0),
    valid_at: int | None = Query(default=None, ge=0),
    limit: int = Query(default=500, ge=1, le=2000),
) -> dict[str, Any]:
    try:
        return world_store.graph(
            auth.tenant_id,
            branch_id=branch_id,
            observed_at=observed_at,
            valid_at=valid_at,
            limit=limit,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/forks")
async def create_world_fork(body: WorldForkCreate, auth: Identity) -> dict[str, Any]:
    try:
        return world_store.create_fork(auth.tenant_id, body)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/forks")
async def world_forks(auth: Identity) -> list[dict[str, Any]]:
    return world_store.list_branches(auth.tenant_id)


@router.get("/diff")
async def world_diff(
    auth: Identity,
    left_branch_id: str = Query(default=REALITY_BRANCH, max_length=100),
    right_branch_id: str = Query(min_length=1, max_length=100),
    observed_at: int | None = Query(default=None, ge=0),
    valid_at: int | None = Query(default=None, ge=0),
) -> dict[str, Any]:
    try:
        return world_store.diff(
            auth.tenant_id,
            left_branch_id=left_branch_id,
            right_branch_id=right_branch_id,
            observed_at=observed_at,
            valid_at=valid_at,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/pulse")
async def world_pulse(
    auth: Identity,
    window_seconds: int = Query(default=3600, ge=60, le=2_592_000),
) -> dict[str, Any]:
    return world_store.pulse(auth.tenant_id, window_seconds=window_seconds)
