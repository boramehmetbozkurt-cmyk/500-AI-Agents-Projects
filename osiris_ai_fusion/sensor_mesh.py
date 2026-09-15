from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from config import get_settings
from reality_atlas import AtlasFeatureCreate, CoordinateSpace, HistoricalDate, TemporalExtent, atlas_store
from saas import AuthContext, require_identity
from world import WorldEventCreate, world_store

logger = logging.getLogger("osiris_fusion.sensor_mesh")

SENSOR_MESH_SOURCES: list[dict[str, Any]] = [
    {
        "id": "fusion_provider_federation",
        "mode": "investigation",
        "role": "Routes read-only finance, crypto, news, science, company, legal and web providers.",
        "automatic": True,
    },
    {
        "id": "fusion_watchlists",
        "mode": "scheduled",
        "role": "Turns recurring investigations into continuously refreshed World observations.",
        "automatic": True,
    },
    {
        "id": "gdelt",
        "mode": "provider_or_gateway",
        "role": "Near-real-time global event and news-knowledge signal.",
        "freshness": "15_minutes",
        "url": "https://gdeltproject.org/",
    },
    {
        "id": "ogc_sensorthings",
        "mode": "provider_or_gateway",
        "role": "Live geospatial IoT and observation streams.",
        "url": "https://www.ogc.org/standards/sensorthings/",
    },
    {
        "id": "openstreetmap",
        "mode": "provider",
        "role": "Present-day physical geography and place context.",
        "url": "https://www.openstreetmap.org/",
    },
    {
        "id": "openhistoricalmap",
        "mode": "historical_import",
        "role": "Historical geography across changing time periods.",
        "url": "https://www.openhistoricalmap.org/",
    },
    {
        "id": "pleiades",
        "mode": "historical_import",
        "role": "Ancient place gazetteer, especially Greek and Roman worlds.",
        "url": "https://pleiades.stoa.org/",
    },
    {
        "id": "openalex_crossref",
        "mode": "provider",
        "role": "Scientific and scholarly knowledge signals.",
        "url": "https://openalex.org/",
    },
]


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _safe_label(query: str) -> str:
    return " ".join(query.split())[:240] or "OSIRIS investigation"


def _evidence_sources(result: dict[str, Any]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    evidence = result.get("evidence", {})
    if not isinstance(evidence, dict):
        return mapping
    for record in evidence.values():
        if not isinstance(record, dict):
            continue
        evidence_id = str(record.get("evidence_id") or "")
        if not evidence_id:
            continue
        sources: list[str] = []
        for key in ("source_url", "provider_id", "tool"):
            value = record.get(key)
            if value:
                sources.append(str(value)[:1000])
        data = record.get("data")
        if isinstance(data, dict):
            source_url = data.get("source_url")
            if source_url:
                sources.append(str(source_url)[:1000])
            providers_used = data.get("providers_used")
            if isinstance(providers_used, list):
                sources.extend(str(item)[:300] for item in providers_used[:16])
        mapping[evidence_id] = list(dict.fromkeys(sources))
    return mapping


def _source_ids_for(evidence_ids: list[str], mapping: dict[str, list[str]]) -> list[str]:
    values: list[str] = []
    for evidence_id in evidence_ids:
        values.extend(mapping.get(evidence_id, []))
    return list(dict.fromkeys(values))[:64]


def _marker_date(marker: dict[str, Any]) -> HistoricalDate:
    raw = marker.get("timestamp")
    dt: datetime | None = None
    if isinstance(raw, (int, float)) and raw >= 0:
        try:
            dt = datetime.fromtimestamp(float(raw), tz=UTC)
        except (OverflowError, OSError, ValueError):
            dt = None
    elif isinstance(raw, str) and raw.strip():
        value = raw.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            dt = None
    if dt is None:
        dt = datetime.now(UTC)
    return HistoricalDate(year=dt.year, month=dt.month, day=dt.day, precision="day", certainty="exact")


class SensorMeshStore:
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
                CREATE TABLE IF NOT EXISTS world_sensor_receipts (
                    workspace_id TEXT NOT NULL,
                    digest TEXT NOT NULL,
                    sensor_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    world_events INTEGER NOT NULL DEFAULT 0,
                    atlas_features INTEGER NOT NULL DEFAULT 0,
                    error TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY(workspace_id, digest)
                );
                CREATE INDEX IF NOT EXISTS idx_world_sensor_receipts
                    ON world_sensor_receipts(workspace_id, created_at DESC);
                """
            )
            conn.commit()

    def begin(self, workspace_id: str, digest: str, sensor_id: str) -> bool:
        now = int(time.time())
        with self._lock, self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO world_sensor_receipts(
                        workspace_id, digest, sensor_id, status, created_at, updated_at
                    ) VALUES (?, ?, ?, 'processing', ?, ?)
                    """,
                    (workspace_id, digest, sensor_id, now, now),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def finish(self, workspace_id: str, digest: str, *, world_events: int, atlas_features: int) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE world_sensor_receipts
                SET status='complete', world_events=?, atlas_features=?, error=NULL, updated_at=?
                WHERE workspace_id=? AND digest=?
                """,
                (world_events, atlas_features, int(time.time()), workspace_id, digest),
            )
            conn.commit()

    def fail(self, workspace_id: str, digest: str, error: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE world_sensor_receipts
                SET status='failed', error=?, updated_at=?
                WHERE workspace_id=? AND digest=?
                """,
                (error[:1000], int(time.time()), workspace_id, digest),
            )
            conn.commit()

    def receipt(self, workspace_id: str, digest: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM world_sensor_receipts WHERE workspace_id=? AND digest=?",
                (workspace_id, digest),
            ).fetchone()
        return dict(row) if row is not None else None

    def list_receipts(self, workspace_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM world_sensor_receipts
                WHERE workspace_id=? ORDER BY created_at DESC LIMIT ?
                """,
                (workspace_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]


sensor_store = SensorMeshStore(get_settings().store_path)


def investigation_digest(query: str, result: dict[str, Any]) -> str:
    report = result.get("report", {})
    claims = report.get("claims", []) if isinstance(report, dict) else []
    markers = report.get("map_markers", []) if isinstance(report, dict) else []
    if not markers:
        markers = result.get("map_markers", [])
    stable = {
        "query": query,
        "evidence_digest": result.get("evidence_digest"),
        "claims": [
            {
                "text": claim.get("text"),
                "kind": claim.get("kind"),
                "confidence": claim.get("confidence"),
                "evidence_ids": claim.get("evidence_ids"),
            }
            for claim in claims
            if isinstance(claim, dict)
        ],
        "markers": markers,
    }
    return _digest(stable)


def ingest_investigation_result(
    workspace_id: str,
    query: str,
    result: dict[str, Any],
    *,
    sensor_id: str = "fusion_investigation",
) -> dict[str, Any]:
    digest = investigation_digest(query, result)
    if not sensor_store.begin(workspace_id, digest, sensor_id):
        return {"status": "duplicate", "digest": digest, "receipt": sensor_store.receipt(workspace_id, digest)}

    world_count = 0
    atlas_count = 0
    try:
        report = result.get("report", {})
        claims = report.get("claims", []) if isinstance(report, dict) else []
        evidence_map = _evidence_sources(result)
        topic_id = f"topic:{hashlib.sha256(query.encode('utf-8')).hexdigest()[:24]}"
        label = _safe_label(query)
        for claim in claims:
            if not isinstance(claim, dict):
                continue
            text = str(claim.get("text") or "").strip()
            evidence_ids = [str(item) for item in claim.get("evidence_ids", []) if str(item).strip()][:32]
            if not text or not evidence_ids:
                continue
            kind = str(claim.get("kind") or "observation")
            statement_kind = "claim" if kind == "observation" else "belief"
            claim_key = hashlib.sha256(text.encode("utf-8")).hexdigest()[:20]
            event = WorldEventCreate(
                entity_id=topic_id,
                entity_type="investigation_topic",
                entity_label=label,
                predicate=f"osiris_assertion:{claim_key}",
                value={"text": text, "analysis_kind": kind},
                statement_kind=statement_kind,
                confidence=float(claim.get("confidence", 0.5)),
                evidence_ids=evidence_ids,
                source_ids=_source_ids_for(evidence_ids, evidence_map),
                metadata={
                    "sensor_id": sensor_id,
                    "sensor_digest": digest,
                    "evidence_bundle_digest": result.get("evidence_digest"),
                },
            )
            world_store.append_event(workspace_id, event)
            world_count += 1

        markers = report.get("map_markers", []) if isinstance(report, dict) else []
        if not markers:
            markers = result.get("map_markers", [])
        seen_markers: set[str] = set()
        for marker in markers if isinstance(markers, list) else []:
            if not isinstance(marker, dict):
                continue
            try:
                lat = float(marker["lat"])
                lon = float(marker["lon"])
            except (KeyError, TypeError, ValueError):
                continue
            evidence_id = str(marker.get("evidence_id") or "")
            signature = _digest(
                {
                    "lat": round(lat, 7),
                    "lon": round(lon, 7),
                    "label": marker.get("label"),
                    "evidence_id": evidence_id,
                    "timestamp": marker.get("timestamp"),
                }
            )
            if signature in seen_markers:
                continue
            seen_markers.add(signature)
            evidence_ids = [evidence_id] if evidence_id else []
            sources = _source_ids_for(evidence_ids, evidence_map)
            if not evidence_ids and not sources:
                continue
            feature = AtlasFeatureCreate(
                feature_id=f"sensor_{signature[:24]}",
                name=str(marker.get("label") or "Observed map feature")[:300],
                feature_type="observed_location",
                realm="physical",
                truth_mode="claim",
                confidence=0.7,
                temporal=TemporalExtent(start=_marker_date(marker)),
                space=CoordinateSpace(space_id="earth:wgs84", kind="earth_geodetic", crs="EPSG:4326"),
                geometry={"type": "Point", "coordinates": [lon, lat]},
                evidence_ids=evidence_ids,
                source_ids=sources,
                metadata={
                    "sensor_id": sensor_id,
                    "sensor_digest": digest,
                    "tool": marker.get("tool"),
                    "query": label,
                },
            )
            atlas_store.upsert_feature(workspace_id, feature)
            atlas_count += 1

        sensor_store.finish(workspace_id, digest, world_events=world_count, atlas_features=atlas_count)
        return {"status": "ingested", "digest": digest, "world_events": world_count, "atlas_features": atlas_count}
    except Exception as exc:
        sensor_store.fail(workspace_id, digest, f"{type(exc).__name__}: {exc}")
        logger.exception("world_sensor_ingest_failed workspace_id=%s digest=%s", workspace_id, digest)
        return {
            "status": "failed",
            "digest": digest,
            "world_events": world_count,
            "atlas_features": atlas_count,
            "error": type(exc).__name__,
        }


router = APIRouter(prefix="/world/sensors", tags=["world-sensors"])
Identity = Annotated[AuthContext, Depends(require_identity)]


@router.get("")
async def sensor_mesh_info(auth: Identity) -> dict[str, Any]:
    return {
        "name": "OSIRIS World Sensor Mesh",
        "workspace_id": auth.tenant_id,
        "mode": "evidence_first_read_only_ingestion",
        "pipeline": [
            "provider_federation",
            "investigation",
            "evidence_sanitization",
            "world_sensor_dedup",
            "world_events",
            "temporal_reality_atlas",
        ],
        "sources": SENSOR_MESH_SOURCES,
    }


@router.get("/sources")
async def sensor_mesh_sources(_: Identity) -> dict[str, Any]:
    return {"sources": SENSOR_MESH_SOURCES}


@router.get("/receipts")
async def sensor_mesh_receipts(auth: Identity, limit: int = Query(default=100, ge=1, le=1000)) -> dict[str, Any]:
    receipts = sensor_store.list_receipts(auth.tenant_id, limit=limit)
    return {"count": len(receipts), "receipts": receipts}
