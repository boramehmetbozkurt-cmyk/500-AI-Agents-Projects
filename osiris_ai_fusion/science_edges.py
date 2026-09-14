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


def _edge_key(source_key: str, relation: str, target_key: str, source_id: str) -> str:
    value = "\x1f".join((source_key, relation, target_key, source_id))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _edge(
    source_key: str,
    relation: str,
    target_key: str,
    source_id: str,
    *,
    confidence: float = 0.9,
    evidence: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "edge_key": _edge_key(source_key, relation, target_key, source_id),
        "source_key": source_key,
        "relation": relation,
        "target_key": target_key,
        "source_id": source_id,
        "confidence": max(0.0, min(1.0, float(confidence))),
        "evidence": evidence or [],
        "metadata": metadata or {},
    }


def derive_edges(entity: dict[str, Any]) -> list[dict[str, Any]]:
    source_key = str(entity.get("canonical_key") or "")
    source_id = str(entity.get("source_id") or "")
    entity_type = str(entity.get("entity_type") or "")
    if not source_key or not source_id:
        return []
    edges: list[dict[str, Any]] = []

    if entity_type == "scientist":
        for institution in entity.get("institutions") or []:
            if not isinstance(institution, dict):
                continue
            institution_id = str(institution.get("id") or "")
            if institution_id:
                edges.append(
                    _edge(
                        source_key,
                        "affiliated_with",
                        f"openalex:institution:{institution_id}",
                        source_id,
                        metadata={"institution_name": institution.get("name")},
                    )
                )
        for topic in entity.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            topic_id = str(topic.get("id") or "")
            if topic_id:
                edges.append(
                    _edge(
                        source_key,
                        "about_topic",
                        f"openalex:topic:{topic_id}",
                        source_id,
                        confidence=float(topic.get("score") or 0.8),
                        metadata={"topic_name": topic.get("name")},
                    )
                )

    if entity_type == "work":
        for author in entity.get("authors") or []:
            if not isinstance(author, dict):
                continue
            author_id = str(author.get("id") or "")
            if author_id:
                edges.append(
                    _edge(
                        f"openalex:author:{author_id}",
                        "authored",
                        source_key,
                        source_id,
                        metadata={
                            "author_name": author.get("name"),
                            "position": author.get("position"),
                            "corresponding": bool(author.get("corresponding")),
                        },
                    )
                )
        for topic in entity.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            topic_id = str(topic.get("id") or "")
            if topic_id:
                edges.append(
                    _edge(
                        source_key,
                        "about_topic",
                        f"openalex:topic:{topic_id}",
                        source_id,
                        confidence=float(topic.get("score") or 0.8),
                        metadata={"topic_name": topic.get("name")},
                    )
                )

    if entity_type == "gene":
        assembly = str(entity.get("assembly_name") or "unknown")
        region = str(entity.get("seq_region_name") or "")
        if region:
            edges.append(
                _edge(
                    source_key,
                    "located_on",
                    f"genome:chromosome:{assembly}:{region}",
                    source_id,
                    metadata={
                        "assembly": assembly,
                        "start": entity.get("start"),
                        "end": entity.get("end"),
                        "strand": entity.get("strand"),
                    },
                )
            )

    if entity_type == "protein":
        organism = entity.get("organism") or {}
        taxon_id = organism.get("taxonId") if isinstance(organism, dict) else None
        for gene in entity.get("genes") or []:
            gene_name = str(gene or "").strip()
            if gene_name:
                gene_key = f"gene-symbol:{taxon_id or 'unknown'}:{gene_name.upper()}"
                edges.append(
                    _edge(
                        gene_key,
                        "encodes",
                        source_key,
                        source_id,
                        metadata={"gene_symbol": gene_name, "taxon_id": taxon_id},
                    )
                )

    if entity_type == "variant":
        for gene in entity.get("genes") or []:
            if not isinstance(gene, dict):
                continue
            symbol = str(gene.get("symbol") or gene.get("name") or "").strip()
            gene_id = str(gene.get("geneid") or gene.get("gene_id") or "").strip()
            if gene_id:
                target = f"ncbi:gene:{gene_id}"
            elif symbol:
                target = f"gene-symbol:9606:{symbol.upper()}"
            else:
                continue
            edges.append(
                _edge(
                    source_key,
                    "associated_with",
                    target,
                    source_id,
                    confidence=0.75,
                    metadata={"relationship": "variant-gene association from source record"},
                )
            )

    return edges


class ScienceEdgeStore:
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
                CREATE TABLE IF NOT EXISTS science_edges (
                    workspace_id TEXT NOT NULL,
                    edge_key TEXT NOT NULL,
                    source_key TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    target_key TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    evidence_json TEXT NOT NULL DEFAULT '[]',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    confidence REAL NOT NULL DEFAULT 0.5,
                    observed_at INTEGER NOT NULL,
                    PRIMARY KEY(workspace_id, edge_key)
                );
                CREATE INDEX IF NOT EXISTS idx_science_edges_nodes_v2
                    ON science_edges(workspace_id, source_key, target_key);
                CREATE INDEX IF NOT EXISTS idx_science_edges_relation
                    ON science_edges(workspace_id, relation, observed_at DESC);
                """
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(science_edges)").fetchall()}
            if "metadata_json" not in columns:
                conn.execute("ALTER TABLE science_edges ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'")
            conn.commit()

    def upsert_edges(self, workspace_id: str, rows: list[dict[str, Any]]) -> int:
        now = int(time.time())
        count = 0
        with self._lock, self._connect() as conn:
            for row in rows:
                if not row.get("edge_key") or not row.get("source_key") or not row.get("target_key"):
                    continue
                conn.execute(
                    """
                    INSERT INTO science_edges(
                        workspace_id, edge_key, source_key, relation, target_key, source_id,
                        evidence_json, metadata_json, confidence, observed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(workspace_id, edge_key) DO UPDATE SET
                        evidence_json=excluded.evidence_json,
                        metadata_json=excluded.metadata_json,
                        confidence=excluded.confidence,
                        observed_at=excluded.observed_at
                    """,
                    (
                        workspace_id,
                        row["edge_key"],
                        row["source_key"],
                        row["relation"],
                        row["target_key"],
                        row["source_id"],
                        json.dumps(row.get("evidence") or [], ensure_ascii=False, sort_keys=True),
                        json.dumps(row.get("metadata") or {}, ensure_ascii=False, sort_keys=True),
                        float(row.get("confidence", 0.5)),
                        now,
                    ),
                )
                count += 1
            conn.commit()
        return count

    def entity_rows(self, workspace_id: str, limit: int = 10000) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM science_entities WHERE workspace_id=? ORDER BY updated_at DESC LIMIT ?",
                (workspace_id, limit),
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def edges(self, workspace_id: str, limit: int = 20000) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT edge_key, source_key, relation, target_key, source_id,
                       evidence_json, metadata_json, confidence, observed_at
                FROM science_edges WHERE workspace_id=?
                ORDER BY observed_at DESC LIMIT ?
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
                "evidence": json.loads(row["evidence_json"]),
                "metadata": json.loads(row["metadata_json"]),
                "confidence": row["confidence"],
                "observed_at": row["observed_at"],
            }
            for row in rows
        ]

    def rebuild(self, workspace_id: str, limit: int = 100000) -> dict[str, int]:
        entities = self.entity_rows(workspace_id, limit=limit)
        edges: list[dict[str, Any]] = []
        for entity in entities:
            edges.extend(derive_edges(entity))
        written = self.upsert_edges(workspace_id, edges)
        return {"entities_scanned": len(entities), "edges_derived": len(edges), "edges_written": written}


edge_store = ScienceEdgeStore(get_settings().store_path)
router = APIRouter(prefix="/science/graph", tags=["science-genome-graph"])
Identity = Annotated[AuthContext, Depends(require_identity)]


@router.get("")
async def science_graph(
    auth: Identity,
    entity_limit: int = Query(default=1000, ge=1, le=10000),
    edge_limit: int = Query(default=5000, ge=1, le=20000),
) -> dict[str, Any]:
    entities = edge_store.entity_rows(auth.tenant_id, limit=entity_limit)
    edges = edge_store.edges(auth.tenant_id, limit=edge_limit)
    return {
        "workspace_id": auth.tenant_id,
        "nodes": entities,
        "edges": edges,
        "node_count": len(entities),
        "edge_count": len(edges),
    }


@router.post("/rebuild")
async def rebuild_science_graph(
    auth: Identity,
    limit: int = Query(default=100000, ge=1, le=1000000),
) -> dict[str, Any]:
    result = edge_store.rebuild(auth.tenant_id, limit=limit)
    return {"workspace_id": auth.tenant_id, "status": "rebuilt", **result}
