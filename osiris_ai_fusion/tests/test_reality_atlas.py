from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

import reality_atlas
import sensor_mesh
from reality_atlas import (
    AtlasFeatureCreate,
    CoordinateSpace,
    HistoricalDate,
    PortalReference,
    RealityAtlasStore,
    TemporalExtent,
)
from sensor_mesh import SensorMeshStore
from world import WorldForkCreate, WorldStore


def _earth_space() -> CoordinateSpace:
    return CoordinateSpace(space_id="earth:wgs84", kind="earth_geodetic", crs="EPSG:4326")


def _historical_feature(**updates: object) -> AtlasFeatureCreate:
    payload: dict[str, object] = {
        "name": "Ancient Ephesus",
        "feature_type": "settlement",
        "realm": "historical_reconstruction",
        "truth_mode": "reconstruction",
        "confidence": 0.9,
        "temporal": TemporalExtent(start=HistoricalDate(year=-500, certainty="circa")),
        "space": _earth_space(),
        "geometry": {"type": "Point", "coordinates": [27.341, 37.939]},
        "source_ids": ["pleiades:599612"],
    }
    payload.update(updates)
    return AtlasFeatureCreate.model_validate(payload)


def test_historical_date_supports_bce_and_rejects_year_zero():
    date = HistoricalDate(year=-458, precision="year", certainty="circa")
    assert date.label() == "458 BCE"
    assert date.start_key() < HistoricalDate(year=1).start_key()
    with pytest.raises(ValidationError):
        HistoricalDate(year=0)


def test_reality_atlas_queries_bce_features_and_keeps_tenants_isolated(tmp_path):
    store = RealityAtlasStore(str(tmp_path / "atlas.sqlite3"))
    store.upsert_feature("tenant-a", _historical_feature(feature_id="shared-place"))
    store.upsert_feature(
        "tenant-b",
        _historical_feature(
            feature_id="shared-place",
            name="Different tenant place",
            geometry={"type": "Point", "coordinates": [10.0, 20.0]},
        ),
    )

    bce = store.query("tenant-a", year=-500)
    assert bce["count"] == 1
    assert bce["features"][0]["name"] == "Ancient Ephesus"
    assert store.query("tenant-a", year=2026)["count"] == 0
    assert store.query("tenant-b", year=-500)["features"][0]["name"] == "Different tenant place"


def test_bbox_and_source_filters_work_for_historical_map(tmp_path):
    store = RealityAtlasStore(str(tmp_path / "atlas.sqlite3"))
    store.upsert_feature("tenant-a", _historical_feature())

    inside = store.query("tenant-a", year=-500, bbox=(26.0, 37.0, 28.0, 39.0))
    outside = store.query("tenant-a", year=-500, bbox=(0.0, 0.0, 1.0, 1.0))
    sourced = store.query("tenant-a", source_id="pleiades:599612")
    assert inside["count"] == 1
    assert outside["count"] == 0
    assert sourced["count"] == 1


def test_future_fact_is_rejected_but_sourced_plan_is_allowed():
    next_year = datetime.now(UTC).year + 1
    with pytest.raises(ValidationError):
        AtlasFeatureCreate(
            name="Future tower",
            feature_type="building",
            realm="physical",
            truth_mode="fact",
            temporal=TemporalExtent(start=HistoricalDate(year=next_year)),
            space=_earth_space(),
            geometry={"type": "Point", "coordinates": [27.1, 38.4]},
            evidence_ids=["ev_future"],
        )

    planned = AtlasFeatureCreate(
        name="Announced future tower",
        feature_type="building",
        realm="physical",
        truth_mode="planned",
        temporal=TemporalExtent(start=HistoricalDate(year=next_year)),
        space=_earth_space(),
        geometry={"type": "Point", "coordinates": [27.1, 38.4]},
        source_ids=["official-plan"],
    )
    assert planned.truth_mode == "planned"


def test_metaverse_spaces_and_cross_realm_portals_are_first_class(tmp_path):
    store = RealityAtlasStore(str(tmp_path / "atlas.sqlite3"))
    feature = AtlasFeatureCreate(
        name="OSIRIS Virtual Agora",
        feature_type="virtual_district",
        realm="metaverse",
        truth_mode="claim",
        temporal=TemporalExtent(start=HistoricalDate(year=2026), open_ended=True),
        space=CoordinateSpace(
            space_id="metaverse:osiris:agora",
            kind="virtual_world",
            platform="osiris-world",
            scene_uri="urn:osiris:scene:agora",
        ),
        local_position=[0.0, 0.0, 0.0],
        portals=[
            PortalReference(
                target_space_id="earth:wgs84",
                target_feature_id="izmir-konak-anchor",
                bidirectional=True,
            )
        ],
        source_ids=["osiris-scene-registry"],
    )
    saved = store.upsert_feature("tenant-a", feature)
    assert saved["space"]["kind"] == "virtual_world"
    portals = store.portals("tenant-a")
    assert portals[0]["target_space_id"] == "earth:wgs84"
    assert portals[0]["bidirectional"] is True


def test_scenario_map_layer_inherits_reality_and_stays_on_fork(tmp_path, monkeypatch):
    path = str(tmp_path / "fork.sqlite3")
    local_world = WorldStore(path)
    local_atlas = RealityAtlasStore(path)
    monkeypatch.setattr(reality_atlas, "world_store", local_world)

    local_atlas.upsert_feature(
        "tenant-a",
        AtlasFeatureCreate(
            feature_id="real-city",
            name="Present City",
            feature_type="city",
            realm="physical",
            truth_mode="fact",
            temporal=TemporalExtent(start=HistoricalDate(year=2020), open_ended=True),
            space=_earth_space(),
            geometry={"type": "Point", "coordinates": [27.1, 38.4]},
            evidence_ids=["official-map"],
        ),
    )
    fork = local_world.create_fork(
        "tenant-a",
        WorldForkCreate(name="Future coast", hypothesis="Alternative 2040 shoreline"),
    )
    local_atlas.upsert_feature(
        "tenant-a",
        AtlasFeatureCreate(
            feature_id="scenario-city",
            name="Scenario City Extension",
            feature_type="planned_district",
            realm="simulation",
            truth_mode="scenario",
            branch_id=fork["id"],
            temporal=TemporalExtent(start=HistoricalDate(year=2040)),
            space=CoordinateSpace(space_id="sim:2040", kind="simulation"),
            local_position=[100.0, 0.0, 200.0],
        ),
    )

    reality = local_atlas.query("tenant-a", year=2040)
    scenario = local_atlas.query("tenant-a", branch_id=fork["id"], year=2040)
    assert {item["id"] for item in reality["features"]} == {"real-city"}
    assert {item["id"] for item in scenario["features"]} == {"real-city", "scenario-city"}


def test_sensor_mesh_ingests_evidence_claims_and_map_markers_once(tmp_path, monkeypatch):
    path = str(tmp_path / "sensor.sqlite3")
    local_world = WorldStore(path)
    local_atlas = RealityAtlasStore(path)
    local_sensor = SensorMeshStore(path)
    monkeypatch.setattr(sensor_mesh, "world_store", local_world)
    monkeypatch.setattr(sensor_mesh, "atlas_store", local_atlas)
    monkeypatch.setattr(sensor_mesh, "sensor_store", local_sensor)

    result = {
        "evidence_digest": "bundle-1",
        "evidence": {
            "provider_federation": {
                "evidence_id": "ev_1",
                "tool": "provider_federation",
                "source_url": "https://example.test/source",
                "ok": True,
                "data": {"providers_used": ["test-provider"]},
            }
        },
        "report": {
            "claims": [
                {
                    "text": "A sourced observation",
                    "kind": "observation",
                    "confidence": 0.88,
                    "evidence_ids": ["ev_1"],
                }
            ],
            "map_markers": [
                {
                    "lat": 38.4237,
                    "lon": 27.1428,
                    "label": "Izmir observation",
                    "evidence_id": "ev_1",
                    "tool": "provider_federation",
                    "timestamp": "2026-09-14T12:00:00Z",
                }
            ],
        },
    }

    first = sensor_mesh.ingest_investigation_result("tenant-a", "What changed?", result)
    second = sensor_mesh.ingest_investigation_result("tenant-a", "What changed?", result)
    assert first["status"] == "ingested"
    assert first["world_events"] == 1
    assert first["atlas_features"] == 1
    assert second["status"] == "duplicate"
    assert local_world.snapshot("tenant-a")["state_count"] == 1
    assert local_atlas.query("tenant-a", year=2026)["count"] == 1
