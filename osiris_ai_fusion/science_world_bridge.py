from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from config import get_settings
from saas import AuthContext, require_identity
from world import REALITY_BRANCH, WorldEventCreate, world_store


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _public_entity_value(entity: dict[str, Any]) -> dict[str, Any]:
    excluded = {"canonical_key", "source_id", "external_id", "entity_type", "name"}
    return {key: value for key, value in entity.items() if key not in excluded}


class ScienceWorldBridgeStore:
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
                CREATE TABLE IF NOT EXISTS science_world_bridge_receipts (
                    workspace_id TEXT NOT NULL,
                    item_kind TEXT NOT NULL,
                    item_key TEXT NOT NULL,
                    item_digest TEXT NOT NULL,
                    world_event_id TEXT NOT NULL,
                    synced_at INTEGER NOT NULL,
                    PRIMARY KEY(workspace_id, item_kind, item_key, item_digest)
                );
                CREATE INDEX IF NOT EXISTS idx_science_world_bridge_receipts
                    ON science_world_bridge_receipts(workspace_id, synced_at DESC);
                """
            )
            conn.commit()

    def _receipt_exists(
        self,
        workspace_id: str,
        item_kind: str,
        item_key: str,
        item_digest: str,
    ) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM science_world_bridge_receipts
                WHERE workspace_id=? AND item_kind=? AND item_key=? AND item_digest=?
                """,
                (workspace_id, item_kind, item_key, item_digest),
            ).fetchone()
        return row is not None

    def _record_receipt(
        self,
        workspace_id: str,
        item_kind: str,
        item_key: str,
        item_digest: str,
        world_event_id: str,
    ) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO science_world_bridge_receipts(
                    workspace_id, item_kind, item_key, item_digest, world_event_id, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    workspace_id,
                    item_kind,
                    item_key,
                    item_digest,
                    world_event_id,
                    int(time.time()),
                ),
            )
            conn.commit()

    def entity_rows(self, workspace_id: str, limit: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM science_entities
                WHERE workspace_id=? ORDER BY updated_at ASC LIMIT ?
                """,
                (workspace_id, limit),
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def edge_rows(self, workspace_id: str, limit: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(science_edges)").fetchall()}
            metadata_expr = "metadata_json" if "metadata_json" in columns else "'{}' AS metadata_json"
            rows = conn.execute(
                f"""
                SELECT edge_key, source_key, relation, target_key, source_id,
                       evidence_json, {metadata_expr}, confidence, observed_at
                FROM science_edges WHERE workspace_id=? ORDER BY observed_at ASC LIMIT ?
                """,
                (workspace_id, limit),
            ).fetchall()
        return [
            {
                "edge_key": row["edge_key"],
                "source_key": row["source_key"],
                "relation": row["relation"],
                "target_key": row["target_key"],
                "source_id": row["source_id"],
                "evidence": json.loads(row["evidence_json"] or "[]"),
                "metadata": json.loads(row["metadata_json"] or "{}"),
                "confidence": float(row["confidence"]),
                "observed_at": int(row["observed_at"]),
            }
            for row in rows
        ]

    def _entity_event(self, entity: dict[str, Any]) -> WorldEventCreate:
        canonical_key = str(entity["canonical_key"])
        source_id = str(entity.get("source_id") or "science_source")
        evidence_id = f"science:{source_id}:{entity.get('external_id') or canonical_key}"
        metadata = {
            "bridge": "science_genome_graph",
            "source_release": entity.get("source_release"),
            "source_file_sha256": entity.get("source_file_sha256"),
            "source_record_digest": entity.get("source_record_digest"),
            "public_reference_only": True,
        }
        return WorldEventCreate(
            entity_id=canonical_key,
            entity_type=str(entity.get("entity_type") or "science_entity"),
            entity_label=str(entity.get("name") or canonical_key)[:240],
            predicate="science_profile",
            value=_public_entity_value(entity),
            statement_kind="claim",
            confidence=0.9,
            evidence_ids=[evidence_id],
            source_ids=[source_id],
            branch_id=REALITY_BRANCH,
            metadata={key: value for key, value in metadata.items() if value is not None},
        )

    def _edge_event(self, edge: dict[str, Any]) -> WorldEventCreate:
        source_id = str(edge.get("source_id") or "science_source")
        evidence = [str(value) for value in edge.get("evidence") or [] if str(value).strip()]
        if not evidence:
            evidence = [f"science-edge:{edge['edge_key']}"]
        return WorldEventCreate(
            entity_id=str(edge["source_key"]),
            entity_type="science_entity",
            entity_label=str(edge["source_key"])[:240],
            predicate=str(edge["relation"])[:160],
            value={"relationship": edge["relation"], "source": source_id},
            statement_kind="claim",
            confidence=float(edge.get("confidence", 0.7)),
            evidence_ids=evidence[:32],
            source_ids=[source_id],
            branch_id=REALITY_BRANCH,
            object_entity_id=str(edge["target_key"]),
            object_entity_type="science_entity",
            object_entity_label=str(edge["target_key"])[:240],
            metadata={
                "bridge": "science_genome_graph",
                "science_edge_key": edge["edge_key"],
                **(edge.get("metadata") or {}),
            },
        )

    def sync(self, workspace_id: str, *, entity_limit: int, edge_limit: int) -> dict[str, int]:
        entities = self.entity_rows(workspace_id, entity_limit)
        edges = self.edge_rows(workspace_id, edge_limit)
        entity_created = 0
        entity_duplicate = 0
        edge_created = 0
        edge_duplicate = 0

        for entity in entities:
            item_key = str(entity.get("canonical_key") or "")
            if not item_key:
                continue
            item_digest = _digest(entity)
            if self._receipt_exists(workspace_id, "entity", item_key, item_digest):
                entity_duplicate += 1
                continue
            event = self._entity_event(entity)
            result = world_store.append_event(workspace_id, event)
            self._record_receipt(
                workspace_id,
                "entity",
                item_key,
                item_digest,
                str(result["id"]),
            )
            entity_created += 1

        for edge in edges:
            item_key = str(edge.get("edge_key") or "")
            if not item_key:
                continue
            item_digest = _digest(edge)
            if self._receipt_exists(workspace_id, "edge", item_key, item_digest):
                edge_duplicate += 1
                continue
            event = self._edge_event(edge)
            result = world_store.append_event(workspace_id, event, observed_at=edge.get("observed_at"))
            self._record_receipt(
                workspace_id,
                "edge",
                item_key,
                item_digest,
                str(result["id"]),
            )
            edge_created += 1

        return {
            "entities_scanned": len(entities),
            "entity_events_created": entity_created,
            "entity_duplicates": entity_duplicate,
            "edges_scanned": len(edges),
            "edge_events_created": edge_created,
            "edge_duplicates": edge_duplicate,
        }

    def receipt_counts(self, workspace_id: str) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT item_kind, COUNT(*) AS n FROM science_world_bridge_receipts
                WHERE workspace_id=? GROUP BY item_kind
                """,
                (workspace_id,),
            ).fetchall()
        return {str(row["item_kind"]): int(row["n"]) for row in rows}


bridge_store = ScienceWorldBridgeStore(get_settings().store_path)
router = APIRouter(prefix="/science/world-bridge", tags=["science-world-bridge"])
Identity = Annotated[AuthContext, Depends(require_identity)]


@router.get("")
async def science_world_bridge_info(auth: Identity) -> dict[str, Any]:
    return {
        "workspace_id": auth.tenant_id,
        "mode": "public_reference_science_to_osiris_world_claims",
        "branch": REALITY_BRANCH,
        "fact_promotion": False,
        "dedup": "content_digest_receipts",
        "receipts": bridge_store.receipt_counts(auth.tenant_id),
        "privacy_boundary": "Personal/patient raw genome data is not accepted by this bridge.",
    }


@router.post("/sync")
async def sync_science_world_bridge(
    auth: Identity,
    entity_limit: int = Query(default=10000, ge=1, le=1000000),
    edge_limit: int = Query(default=20000, ge=1, le=1000000),
) -> dict[str, Any]:
    result = bridge_store.sync(
        auth.tenant_id,
        entity_limit=entity_limit,
        edge_limit=edge_limit,
    )
    return {"workspace_id": auth.tenant_id, "status": "synced", **result}
