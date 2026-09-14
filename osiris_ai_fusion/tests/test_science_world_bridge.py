import science_world_bridge as bridge_module
from science_edges import ScienceEdgeStore
from science_world import ScienceGraphStore
from science_world_bridge import ScienceWorldBridgeStore
from world import WorldStore


def test_science_world_bridge_syncs_claims_and_deduplicates(tmp_path, monkeypatch):
    db = str(tmp_path / "fusion.sqlite3")
    graph = ScienceGraphStore(db)
    edges = ScienceEdgeStore(db)
    world = WorldStore(db)
    bridge = ScienceWorldBridgeStore(db)
    monkeypatch.setattr(bridge_module, "world_store", world)

    graph.upsert_entities(
        "tenant-a",
        [
            {
                "entity_type": "scientist",
                "canonical_key": "openalex:author:A1",
                "source_id": "openalex",
                "external_id": "A1",
                "name": "Researcher One",
                "works_count": 4,
                "source_release": "2026-09",
                "source_file_sha256": "abc",
                "source_record_digest": "record-digest",
            },
            {
                "entity_type": "work",
                "canonical_key": "openalex:work:W1",
                "source_id": "openalex",
                "external_id": "W1",
                "name": "Genome Study",
                "authors": [{"id": "A1", "name": "Researcher One"}],
            },
        ],
    )
    edges.rebuild("tenant-a")

    first = bridge.sync("tenant-a", entity_limit=100, edge_limit=100)
    second = bridge.sync("tenant-a", entity_limit=100, edge_limit=100)

    assert first["entity_events_created"] == 2
    assert first["edge_events_created"] == 1
    assert second["entity_events_created"] == 0
    assert second["edge_events_created"] == 0
    assert second["entity_duplicates"] == 2
    assert second["edge_duplicates"] == 1

    snapshot = world.snapshot("tenant-a")
    assertions = [item for item in snapshot["states"] if item["predicate"] == "science_profile"]
    assert len(assertions) == 2
    assert all(item["effective"]["statement_kind"] == "claim" for item in assertions)
    assert all(item["effective"]["source_ids"] == ["openalex"] for item in assertions)


def test_bridge_is_tenant_scoped(tmp_path, monkeypatch):
    db = str(tmp_path / "fusion.sqlite3")
    graph = ScienceGraphStore(db)
    world = WorldStore(db)
    bridge = ScienceWorldBridgeStore(db)
    monkeypatch.setattr(bridge_module, "world_store", world)

    graph.upsert_entities(
        "tenant-a",
        [
            {
                "entity_type": "gene",
                "canonical_key": "ensembl:gene:ENSG1",
                "source_id": "ensembl",
                "external_id": "ENSG1",
                "name": "GENE1",
            }
        ],
    )
    bridge.sync("tenant-a", entity_limit=10, edge_limit=10)
    bridge.sync("tenant-b", entity_limit=10, edge_limit=10)

    assert bridge.receipt_counts("tenant-a") == {"entity": 1}
    assert bridge.receipt_counts("tenant-b") == {}
    assert world.snapshot("tenant-b")["states"] == []
