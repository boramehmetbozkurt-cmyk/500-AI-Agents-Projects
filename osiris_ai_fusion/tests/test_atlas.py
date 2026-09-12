from __future__ import annotations

import json
from pathlib import Path


ASSETS = Path(__file__).resolve().parents[1] / "ui" / "assets"
MAP_FILES = {
    "ai-universe": "atlas-ai-universe.json",
    "ai-gene": "atlas-ai-gene.json",
    "agi": "atlas-agi.json",
    "meta-universe": "atlas-meta-universe.json",
    "btc-universe": "atlas-btc-universe.json",
    "money-universe": "atlas-money-universe.json",
}


def _load(name: str) -> dict:
    return json.loads((ASSETS / name).read_text(encoding="utf-8"))


def test_all_six_atlas_maps_exist_and_have_expected_ids():
    for expected_id, filename in MAP_FILES.items():
        payload = _load(filename)
        assert payload["id"] == expected_id
        assert payload.get("title")
        assert payload.get("nodes")
        assert payload.get("edges") is not None


def test_atlas_graph_integrity_and_provenance_references():
    meta = _load("atlas-meta.json")
    source_ids = set(meta["sources"])

    for filename in MAP_FILES.values():
        payload = _load(filename)
        nodes = payload["nodes"]
        edges = payload["edges"]
        node_ids = [node["id"] for node in nodes]

        assert len(node_ids) == len(set(node_ids)), f"duplicate node id in {filename}"
        known_nodes = set(node_ids)

        for node in nodes:
            confidence = float(node.get("confidence", 0))
            assert 0 <= confidence <= 1
            for source_id in node.get("source_ids", []):
                assert source_id in source_ids, f"unknown source {source_id} in {filename}"

        for edge in edges:
            assert edge["source"] in known_nodes, f"unknown edge source in {filename}"
            assert edge["target"] in known_nodes, f"unknown edge target in {filename}"
            confidence = float(edge.get("confidence", 0))
            assert 0 <= confidence <= 1
            for source_id in edge.get("source_ids", []):
                assert source_id in source_ids, f"unknown edge source ref {source_id} in {filename}"


def test_btc_and_money_maps_are_sourced_research_context():
    meta = _load("atlas-meta.json")
    policy = meta["source_policy"].lower()
    assert "not investment advice" in policy

    btc = _load(MAP_FILES["btc-universe"])
    money = _load(MAP_FILES["money-universe"])
    assert "btc" in btc["title"].lower() or "bitcoin" in btc["title"].lower()
    assert "money" in money["title"].lower()
    assert any(node.get("source_ids") for node in btc["nodes"])
    assert any(node.get("source_ids") for node in money["nodes"])
