from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator, model_validator

from config import get_settings
from saas import AuthContext, require_identity
from world import REALITY_BRANCH, world_store

RealmKind = Literal[
    "physical",
    "historical_reconstruction",
    "digital_twin",
    "mixed_reality",
    "metaverse",
    "simulation",
]
TruthMode = Literal["fact", "claim", "belief", "reconstruction", "planned", "scenario"]
TemporalPrecision = Literal["day", "month", "year", "decade", "century", "millennium", "unknown"]
TemporalCertainty = Literal["exact", "circa", "estimated", "earliest", "latest", "disputed", "scenario"]
SpaceKind = Literal[
    "earth_geodetic",
    "earth_projected",
    "indoor_local",
    "digital_twin",
    "mixed_reality",
    "virtual_world",
    "simulation",
    "celestial",
]


class HistoricalDate(BaseModel):
    """Signed historical date. Negative years are BCE; positive years are CE."""

    year: int = Field(ge=-2_000_000, le=2_000_000)
    month: int | None = Field(default=None, ge=1, le=12)
    day: int | None = Field(default=None, ge=1, le=31)
    precision: TemporalPrecision = "year"
    certainty: TemporalCertainty = "exact"
    calendar: str = Field(default="proleptic_gregorian", max_length=80)
    uncertainty_years: int = Field(default=0, ge=0, le=1_000_000)

    @field_validator("year")
    @classmethod
    def no_year_zero(cls, value: int) -> int:
        if value == 0:
            raise ValueError("year 0 is not used; use -1 for 1 BCE and 1 for 1 CE")
        return value

    @model_validator(mode="after")
    def validate_precision(self) -> HistoricalDate:
        if self.day is not None and self.month is None:
            raise ValueError("day requires month")
        if self.precision == "day" and (self.month is None or self.day is None):
            raise ValueError("day precision requires month and day")
        if self.precision == "month" and self.month is None:
            raise ValueError("month precision requires month")
        return self

    def start_key(self) -> int:
        month = self.month or 1
        day = self.day or 1
        return self.year * 10_000 + month * 100 + day

    def end_key(self) -> int:
        if self.precision in {"unknown", "millennium", "century", "decade", "year"}:
            month, day = 12, 31
        elif self.precision == "month":
            month, day = self.month or 12, 31
        else:
            month, day = self.month or 12, self.day or 31
        return self.year * 10_000 + month * 100 + day

    def label(self) -> str:
        era = "BCE" if self.year < 0 else "CE"
        absolute = abs(self.year)
        if self.month is None:
            return f"{absolute} {era}"
        if self.day is None:
            return f"{absolute:04d}-{self.month:02d} {era}"
        return f"{absolute:04d}-{self.month:02d}-{self.day:02d} {era}"


class TemporalExtent(BaseModel):
    start: HistoricalDate | None = None
    end: HistoricalDate | None = None
    open_ended: bool = False

    @model_validator(mode="after")
    def validate_order(self) -> TemporalExtent:
        if self.open_ended and self.end is not None:
            raise ValueError("open_ended intervals cannot also define end")
        if self.open_ended and self.start is None:
            raise ValueError("open_ended intervals require start")
        if self.start and self.end and self.start.start_key() > self.end.end_key():
            raise ValueError("temporal end must not precede start")
        return self


class GeoPoseAnchor(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    height_m: float = 0.0
    yaw_deg: float = 0.0
    pitch_deg: float = 0.0
    roll_deg: float = 0.0
    reference_frame: str = Field(default="EPSG:4979", max_length=120)


class CoordinateSpace(BaseModel):
    space_id: str = Field(min_length=1, max_length=200)
    kind: SpaceKind
    crs: str | None = Field(default=None, max_length=160)
    parent_space_id: str | None = Field(default=None, max_length=200)
    platform: str | None = Field(default=None, max_length=160)
    scene_uri: str | None = Field(default=None, max_length=1000)
    earth_anchor: GeoPoseAnchor | None = None
    local_origin: list[float] | None = Field(default=None, min_length=3, max_length=3)
    local_axes: str = Field(default="right-handed-y-up", max_length=80)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AssetReference(BaseModel):
    uri: str = Field(min_length=1, max_length=2000)
    format: str = Field(min_length=1, max_length=80)
    media_type: str | None = Field(default=None, max_length=160)
    lod: str | None = Field(default=None, max_length=80)
    checksum: str | None = Field(default=None, max_length=160)
    source_id: str | None = Field(default=None, max_length=300)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PortalReference(BaseModel):
    target_space_id: str = Field(min_length=1, max_length=200)
    target_feature_id: str | None = Field(default=None, max_length=200)
    bidirectional: bool = False
    transform_4x4: list[float] | None = Field(default=None, min_length=16, max_length=16)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AtlasFeatureCreate(BaseModel):
    feature_id: str | None = Field(default=None, max_length=200)
    name: str = Field(min_length=1, max_length=300)
    feature_type: str = Field(min_length=1, max_length=160)
    realm: RealmKind = "physical"
    truth_mode: TruthMode = "claim"
    branch_id: str = Field(default=REALITY_BRANCH, min_length=1, max_length=100)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    temporal: TemporalExtent = Field(default_factory=TemporalExtent)
    space: CoordinateSpace
    geometry: dict[str, Any] | None = None
    local_position: list[float] | None = Field(default=None, min_length=3, max_length=3)
    assets: list[AssetReference] = Field(default_factory=list, max_length=64)
    portals: list[PortalReference] = Field(default_factory=list, max_length=32)
    evidence_ids: list[str] = Field(default_factory=list, max_length=64)
    source_ids: list[str] = Field(default_factory=list, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_semantics(self) -> AtlasFeatureCreate:
        if self.truth_mode == "fact" and not self.evidence_ids:
            raise ValueError("Atlas facts require at least one evidence_id")
        if (
            self.branch_id == REALITY_BRANCH
            and self.truth_mode in {"claim", "reconstruction", "planned"}
            and not (self.evidence_ids or self.source_ids)
        ):
            raise ValueError("Reality claims, reconstructions and plans require evidence or source IDs")
        if self.truth_mode == "scenario" and self.branch_id == REALITY_BRANCH:
            raise ValueError("Scenario features require a fork branch")
        if self.branch_id != REALITY_BRANCH and self.truth_mode == "fact":
            raise ValueError("Fork branches cannot create new facts")
        current_year = datetime.now(UTC).year
        if (
            self.branch_id == REALITY_BRANCH
            and self.truth_mode == "fact"
            and self.temporal.start is not None
            and self.temporal.start.year > current_year
        ):
            raise ValueError("Future states cannot be facts on the reality branch")
        if self.geometry is None and self.local_position is None and self.space.earth_anchor is None:
            raise ValueError("Map features require geometry, local_position or an earth_anchor")
        if self.local_position is not None and self.space.kind == "earth_geodetic":
            raise ValueError("earth_geodetic features should use GeoJSON geometry or GeoPose anchor")
        return self


class AtlasBatchCreate(BaseModel):
    features: list[AtlasFeatureCreate] = Field(min_length=1, max_length=250)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _bbox_from_coordinates(value: Any) -> tuple[float, float, float, float] | None:
    points: list[tuple[float, float]] = []

    def walk(item: Any) -> None:
        if isinstance(item, (list, tuple)):
            if (
                len(item) >= 2
                and isinstance(item[0], (int, float))
                and isinstance(item[1], (int, float))
            ):
                points.append((float(item[0]), float(item[1])))
                return
            for child in item:
                walk(child)

    walk(value)
    if not points:
        return None
    lons = [point[0] for point in points]
    lats = [point[1] for point in points]
    return min(lons), min(lats), max(lons), max(lats)


def _geometry_bbox(geometry: dict[str, Any] | None) -> tuple[float, float, float, float] | None:
    if not geometry:
        return None
    geometry_type = str(geometry.get("type", ""))
    if geometry_type not in {
        "Point",
        "MultiPoint",
        "LineString",
        "MultiLineString",
        "Polygon",
        "MultiPolygon",
        "GeometryCollection",
    }:
        raise ValueError("Unsupported GeoJSON geometry type")
    if geometry_type == "GeometryCollection":
        boxes = [
            _geometry_bbox(item)
            for item in geometry.get("geometries", [])
            if isinstance(item, dict)
        ]
        present = [box for box in boxes if box is not None]
        if not present:
            return None
        return (
            min(box[0] for box in present),
            min(box[1] for box in present),
            max(box[2] for box in present),
            max(box[3] for box in present),
        )
    return _bbox_from_coordinates(geometry.get("coordinates"))


ATLAS_LAYERS: list[dict[str, Any]] = [
    {
        "id": "deep-time",
        "label": "Deep Time / Prehistory",
        "range": {"start_year": -2_000_000, "end_year": -3001},
        "truth_modes": ["claim", "reconstruction"],
    },
    {
        "id": "ancient-world",
        "label": "Ancient World",
        "range": {"start_year": -3000, "end_year": 499},
        "truth_modes": ["fact", "claim", "reconstruction"],
    },
    {
        "id": "medieval-early-modern",
        "label": "Medieval / Early Modern",
        "range": {"start_year": 500, "end_year": 1799},
        "truth_modes": ["fact", "claim", "reconstruction"],
    },
    {
        "id": "industrial-modern",
        "label": "Industrial / Modern",
        "range": {"start_year": 1800, "end_year": 1999},
        "truth_modes": ["fact", "claim", "reconstruction"],
    },
    {
        "id": "digital-era",
        "label": "Digital Era",
        "range": {"start_year": 2000, "end_year": datetime.now(UTC).year},
        "truth_modes": ["fact", "claim", "belief"],
    },
    {
        "id": "near-future",
        "label": "Near Future",
        "range": {"start_year": datetime.now(UTC).year + 1, "end_year": 2100},
        "truth_modes": ["planned", "scenario", "belief"],
    },
    {
        "id": "far-future",
        "label": "Far Future",
        "range": {"start_year": 2101, "end_year": 2_000_000},
        "truth_modes": ["scenario", "belief"],
    },
]

ATLAS_STANDARDS: list[dict[str, Any]] = [
    {"id": "geosparql-1.1", "role": "semantic_geospatial_graph", "url": "https://www.ogc.org/standards/geosparql/"},
    {"id": "ogc-api-features-1.0", "role": "web_feature_query", "url": "https://www.ogc.org/standards/ogcapi-features/"},
    {"id": "ogc-api-tiles-1.0", "role": "2d_and_vector_tile_delivery", "url": "https://www.ogc.org/standards/ogcapi-tiles/"},
    {"id": "3d-tiles-1.1", "role": "planet_scale_3d_streaming", "url": "https://www.ogc.org/standards/3dtiles/"},
    {"id": "citygml-3.0", "role": "semantic_3d_city_and_digital_twin", "url": "https://www.ogc.org/standards/citygml/"},
    {"id": "geopose-1.0", "role": "real_virtual_pose_and_reference_frames", "url": "https://www.ogc.org/standards/geopose/"},
    {"id": "sensorthings-1.1", "role": "live_geospatial_sensor_observations", "url": "https://www.ogc.org/standards/sensorthings/"},
    {"id": "stac", "role": "spatiotemporal_asset_catalog", "url": "https://stacspec.org/"},
    {"id": "gltf-2.x", "role": "runtime_3d_asset_delivery", "url": "https://registry.khronos.org/glTF/"},
    {"id": "openusd-core-1.0", "role": "composable_3d_world_scene_description", "url": "https://aousd.org/usd-core-specification/"},
]

ATLAS_SOURCES: list[dict[str, Any]] = [
    {
        "id": "pleiades",
        "coverage": "ancient_places",
        "realms": ["physical", "historical_reconstruction"],
        "url": "https://pleiades.stoa.org/",
        "license_note": "CC BY; preserve attribution and source identifiers.",
    },
    {
        "id": "openhistoricalmap",
        "coverage": "historical_human_and_natural_geography",
        "realms": ["physical", "historical_reconstruction"],
        "url": "https://www.openhistoricalmap.org/",
        "license_note": "Public-domain/CC0 oriented; verify per-record attribution where noted.",
    },
    {
        "id": "wikidata",
        "coverage": "linked_entities_dates_and_date_uncertainty",
        "realms": ["physical", "historical_reconstruction"],
        "url": "https://www.wikidata.org/",
        "license_note": "Preserve item identifiers and provenance references.",
    },
    {
        "id": "openstreetmap",
        "coverage": "present_day_map_features",
        "realms": ["physical"],
        "url": "https://www.openstreetmap.org/",
        "license_note": "ODbL; attribution and share-alike database obligations apply.",
    },
    {
        "id": "gdelt",
        "coverage": "near_realtime_global_events_and_news_knowledge_graph",
        "realms": ["physical"],
        "url": "https://gdeltproject.org/",
        "license_note": "Use provider documentation and preserve upstream source links.",
    },
    {
        "id": "openalex",
        "coverage": "scholarly_knowledge_graph",
        "realms": ["physical", "digital_twin"],
        "url": "https://openalex.org/",
        "license_note": "Preserve work/source identifiers and provider attribution.",
    },
    {
        "id": "crossref",
        "coverage": "scholarly_metadata",
        "realms": ["physical", "digital_twin"],
        "url": "https://www.crossref.org/",
        "license_note": "Metadata is broadly reusable; individual abstracts can have separate rights.",
    },
]


class RealityAtlasStore:
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
                CREATE TABLE IF NOT EXISTS reality_atlas_features (
                    id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    branch_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    feature_type TEXT NOT NULL,
                    realm TEXT NOT NULL,
                    truth_mode TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    temporal_json TEXT NOT NULL,
                    start_key INTEGER,
                    end_key INTEGER,
                    space_json TEXT NOT NULL,
                    geometry_json TEXT,
                    local_position_json TEXT,
                    min_lon REAL,
                    min_lat REAL,
                    max_lon REAL,
                    max_lat REAL,
                    assets_json TEXT NOT NULL,
                    portals_json TEXT NOT NULL,
                    evidence_ids_json TEXT NOT NULL,
                    source_ids_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY(workspace_id, id)
                );
                CREATE INDEX IF NOT EXISTS idx_reality_atlas_scope
                    ON reality_atlas_features(workspace_id, branch_id, realm, feature_type);
                CREATE INDEX IF NOT EXISTS idx_reality_atlas_time
                    ON reality_atlas_features(workspace_id, start_key, end_key);
                CREATE INDEX IF NOT EXISTS idx_reality_atlas_bbox
                    ON reality_atlas_features(workspace_id, min_lon, min_lat, max_lon, max_lat);
                """
            )
            conn.commit()

    @staticmethod
    def _stable_feature_id(workspace_id: str, feature: AtlasFeatureCreate) -> str:
        if feature.feature_id:
            return feature.feature_id
        stable = {
            "workspace_id": workspace_id,
            "name": feature.name,
            "feature_type": feature.feature_type,
            "realm": feature.realm,
            "branch_id": feature.branch_id,
            "space_id": feature.space.space_id,
            "temporal": feature.temporal.model_dump(mode="json"),
            "geometry": feature.geometry,
            "local_position": feature.local_position,
            "sources": feature.source_ids,
        }
        digest = hashlib.sha256(_json(stable).encode("utf-8")).hexdigest()[:24]
        return f"atlas_{digest}"

    def upsert_feature(self, workspace_id: str, feature: AtlasFeatureCreate) -> dict[str, Any]:
        if feature.branch_id != REALITY_BRANCH:
            world_store.get_branch(workspace_id, feature.branch_id)
        feature_id = self._stable_feature_id(workspace_id, feature)
        bbox = _geometry_bbox(feature.geometry)
        if bbox is None and feature.space.earth_anchor is not None:
            anchor = feature.space.earth_anchor
            bbox = (anchor.longitude, anchor.latitude, anchor.longitude, anchor.latitude)
        start_key = feature.temporal.start.start_key() if feature.temporal.start else None
        if feature.temporal.end is not None:
            end_key = feature.temporal.end.end_key()
        elif feature.temporal.open_ended:
            end_key = None
        else:
            end_key = feature.temporal.start.end_key() if feature.temporal.start else None
        now = int(time.time())
        values = (
            feature_id, workspace_id, feature.branch_id, feature.name, feature.feature_type,
            feature.realm, feature.truth_mode, feature.confidence,
            _json(feature.temporal.model_dump(mode="json")), start_key, end_key,
            _json(feature.space.model_dump(mode="json")),
            _json(feature.geometry) if feature.geometry is not None else None,
            _json(feature.local_position) if feature.local_position is not None else None,
            bbox[0] if bbox else None, bbox[1] if bbox else None,
            bbox[2] if bbox else None, bbox[3] if bbox else None,
            _json([item.model_dump(mode="json") for item in feature.assets]),
            _json([item.model_dump(mode="json") for item in feature.portals]),
            _json(feature.evidence_ids), _json(feature.source_ids), _json(feature.metadata), now,
        )
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO reality_atlas_features(
                    id, workspace_id, branch_id, name, feature_type, realm, truth_mode,
                    confidence, temporal_json, start_key, end_key, space_json, geometry_json,
                    local_position_json, min_lon, min_lat, max_lon, max_lat, assets_json,
                    portals_json, evidence_ids_json, source_ids_json, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(workspace_id, id) DO UPDATE SET
                    name=excluded.name, feature_type=excluded.feature_type,
                    realm=excluded.realm, truth_mode=excluded.truth_mode,
                    confidence=excluded.confidence, temporal_json=excluded.temporal_json,
                    start_key=excluded.start_key, end_key=excluded.end_key,
                    space_json=excluded.space_json, geometry_json=excluded.geometry_json,
                    local_position_json=excluded.local_position_json,
                    min_lon=excluded.min_lon, min_lat=excluded.min_lat,
                    max_lon=excluded.max_lon, max_lat=excluded.max_lat,
                    assets_json=excluded.assets_json, portals_json=excluded.portals_json,
                    evidence_ids_json=excluded.evidence_ids_json,
                    source_ids_json=excluded.source_ids_json, metadata_json=excluded.metadata_json
                """,
                values,
            )
            conn.commit()
        return self.get_feature(workspace_id, feature_id)

    def upsert_batch(self, workspace_id: str, features: list[AtlasFeatureCreate]) -> list[dict[str, Any]]:
        return [self.upsert_feature(workspace_id, feature) for feature in features]

    @staticmethod
    def _decode(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        item = dict(row)
        item["temporal"] = json.loads(item.pop("temporal_json"))
        item["space"] = json.loads(item.pop("space_json"))
        item["geometry"] = json.loads(item["geometry_json"]) if item.get("geometry_json") else None
        item.pop("geometry_json", None)
        item["local_position"] = json.loads(item["local_position_json"]) if item.get("local_position_json") else None
        item.pop("local_position_json", None)
        for key in ("assets", "portals", "evidence_ids", "source_ids", "metadata"):
            item[key] = json.loads(item.pop(f"{key}_json"))
        return item

    def get_feature(self, workspace_id: str, feature_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM reality_atlas_features WHERE workspace_id=? AND id=?",
                (workspace_id, feature_id),
            ).fetchone()
        if row is None:
            raise KeyError(feature_id)
        return self._decode(row)

    def _branch_lineage_ids(self, workspace_id: str, branch_id: str) -> list[str]:
        if branch_id == REALITY_BRANCH:
            return [REALITY_BRANCH]
        branch = world_store.get_branch(workspace_id, branch_id)
        return [*self._branch_lineage_ids(workspace_id, str(branch["parent_branch_id"])), branch_id]

    def query(
        self,
        workspace_id: str,
        *,
        branch_id: str = REALITY_BRANCH,
        year: int | None = None,
        realm: str | None = None,
        feature_type: str | None = None,
        bbox: tuple[float, float, float, float] | None = None,
        source_id: str | None = None,
        limit: int = 500,
    ) -> dict[str, Any]:
        branches = self._branch_lineage_ids(workspace_id, branch_id)
        placeholders = ",".join("?" for _ in branches)
        sql = f"SELECT * FROM reality_atlas_features WHERE workspace_id=? AND branch_id IN ({placeholders})"
        params: list[Any] = [workspace_id, *branches]
        if year is not None:
            if year == 0:
                raise ValueError("year 0 is invalid")
            point = year * 10_000 + 101
            sql += " AND (start_key IS NULL OR start_key<=?) AND (end_key IS NULL OR end_key>=?)"
            params.extend([point, point])
        if realm:
            sql += " AND realm=?"
            params.append(realm)
        if feature_type:
            sql += " AND feature_type=?"
            params.append(feature_type)
        if bbox:
            min_lon, min_lat, max_lon, max_lat = bbox
            if min_lon > max_lon or min_lat > max_lat:
                raise ValueError("Invalid bbox ordering")
            sql += " AND min_lon IS NOT NULL AND max_lon>=? AND min_lon<=? AND max_lat>=? AND min_lat<=?"
            params.extend([min_lon, max_lon, min_lat, max_lat])
        if source_id:
            sql += " AND source_ids_json LIKE ?"
            params.append(f'%\"{source_id}\"%')
        sql += " ORDER BY start_key ASC, created_at ASC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return {
            "workspace_id": workspace_id,
            "branch_id": branch_id,
            "year": year,
            "realm": realm,
            "feature_type": feature_type,
            "bbox": bbox,
            "count": len(rows),
            "features": [self._decode(row) for row in rows],
        }

    def portals(self, workspace_id: str, *, branch_id: str = REALITY_BRANCH, limit: int = 500) -> list[dict[str, Any]]:
        result = self.query(workspace_id, branch_id=branch_id, limit=limit)
        links: list[dict[str, Any]] = []
        for feature in result["features"]:
            for portal in feature["portals"]:
                links.append({"source_feature_id": feature["id"], "source_space_id": feature["space"]["space_id"], **portal})
        return links

    def timeline(self, workspace_id: str, *, branch_id: str = REALITY_BRANCH) -> dict[str, Any]:
        result = self.query(workspace_id, branch_id=branch_id, limit=10_000)
        bands: list[dict[str, Any]] = []
        for layer in ATLAS_LAYERS:
            start_year = int(layer["range"]["start_year"])
            end_year = int(layer["range"]["end_year"])
            count = 0
            realms: dict[str, int] = {}
            for feature in result["features"]:
                temporal = feature["temporal"]
                start = temporal.get("start")
                end = temporal.get("end")
                feature_start = int(start["year"]) if start else -2_000_000
                feature_end = int(end["year"]) if end else (2_000_000 if temporal.get("open_ended") else feature_start)
                if feature_end < start_year or feature_start > end_year:
                    continue
                count += 1
                realms[feature["realm"]] = realms.get(feature["realm"], 0) + 1
            bands.append({**layer, "count": count, "realms": realms})
        return {"workspace_id": workspace_id, "branch_id": branch_id, "bands": bands}


settings = get_settings()
atlas_store = RealityAtlasStore(settings.store_path)
router = APIRouter(prefix="/world/atlas", tags=["world-atlas"])
Identity = Annotated[AuthContext, Depends(require_identity)]


@router.get("")
async def atlas_info(auth: Identity) -> dict[str, Any]:
    return {
        "name": "OSIRIS Temporal Reality Atlas",
        "workspace_id": auth.tenant_id,
        "temporal_range": {"min_year": -2_000_000, "max_year": 2_000_000, "year_zero": False},
        "realms": ["physical", "historical_reconstruction", "digital_twin", "mixed_reality", "metaverse", "simulation"],
        "principles": [
            "bce_to_future_temporal_index",
            "physical_and_virtual_coordinate_spaces",
            "future_is_planned_or_scenario_not_fact",
            "evidence_bound_facts",
            "fork_aware_map_layers",
            "cross_realm_portals",
            "open_3d_and_geospatial_standards",
        ],
    }


@router.get("/standards")
async def atlas_standards(_: Identity) -> dict[str, Any]:
    return {"standards": ATLAS_STANDARDS}


@router.get("/sources")
async def atlas_sources(_: Identity) -> dict[str, Any]:
    return {"sources": ATLAS_SOURCES}


@router.get("/layers")
async def atlas_layers(_: Identity) -> dict[str, Any]:
    return {"layers": ATLAS_LAYERS}


@router.post("/features")
async def create_atlas_feature(body: AtlasFeatureCreate, auth: Identity) -> dict[str, Any]:
    try:
        return atlas_store.upsert_feature(auth.tenant_id, body)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/features/batch")
async def create_atlas_features(body: AtlasBatchCreate, auth: Identity) -> dict[str, Any]:
    try:
        features = atlas_store.upsert_batch(auth.tenant_id, body.features)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"count": len(features), "features": features}


@router.get("/features")
async def query_atlas_features(
    auth: Identity,
    branch_id: str = Query(default=REALITY_BRANCH, max_length=100),
    year: int | None = Query(default=None, ge=-2_000_000, le=2_000_000),
    realm: RealmKind | None = Query(default=None),
    feature_type: str | None = Query(default=None, max_length=160),
    min_lon: float | None = Query(default=None, ge=-180, le=180),
    min_lat: float | None = Query(default=None, ge=-90, le=90),
    max_lon: float | None = Query(default=None, ge=-180, le=180),
    max_lat: float | None = Query(default=None, ge=-90, le=90),
    source_id: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=500, ge=1, le=5000),
) -> dict[str, Any]:
    bbox_values = (min_lon, min_lat, max_lon, max_lat)
    if any(item is not None for item in bbox_values) and not all(item is not None for item in bbox_values):
        raise HTTPException(status_code=400, detail="bbox requires min_lon,min_lat,max_lon,max_lat")
    bbox = tuple(float(item) for item in bbox_values) if all(item is not None for item in bbox_values) else None
    try:
        return atlas_store.query(
            auth.tenant_id,
            branch_id=branch_id,
            year=year,
            realm=realm,
            feature_type=feature_type,
            bbox=bbox,
            source_id=source_id,
            limit=limit,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/timeline")
async def atlas_timeline(auth: Identity, branch_id: str = Query(default=REALITY_BRANCH, max_length=100)) -> dict[str, Any]:
    try:
        return atlas_store.timeline(auth.tenant_id, branch_id=branch_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/portals")
async def atlas_portals(
    auth: Identity,
    branch_id: str = Query(default=REALITY_BRANCH, max_length=100),
    limit: int = Query(default=500, ge=1, le=5000),
) -> dict[str, Any]:
    try:
        links = atlas_store.portals(auth.tenant_id, branch_id=branch_id, limit=limit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"count": len(links), "portals": links}
