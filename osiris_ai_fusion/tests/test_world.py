from __future__ import annotations

import pytest
from pydantic import ValidationError

from world import REALITY_BRANCH, WorldEventCreate, WorldForkCreate, WorldStore


def _fact(value: object, **kwargs: object) -> WorldEventCreate:
    return WorldEventCreate(
        entity_id=str(kwargs.pop("entity_id", "btc")),
        entity_type=str(kwargs.pop("entity_type", "crypto")),
        entity_label=str(kwargs.pop("entity_label", "Bitcoin")),
        predicate=str(kwargs.pop("predicate", "price_usd")),
        value=value,
        statement_kind="fact",
        confidence=float(kwargs.pop("confidence", 0.99)),
        evidence_ids=list(kwargs.pop("evidence_ids", ["ev_1"])),
        **kwargs,
    )


def test_fact_requires_evidence_and_assumption_cannot_enter_reality():
    with pytest.raises(ValidationError):
        WorldEventCreate(
            entity_id="btc",
            entity_type="crypto",
            predicate="price_usd",
            value=100_000,
            statement_kind="fact",
        )

    with pytest.raises(ValidationError):
        WorldEventCreate(
            entity_id="turkey-rate",
            entity_type="macro",
            predicate="policy_rate",
            value=20,
            statement_kind="assumption",
            branch_id=REALITY_BRANCH,
        )


def test_bitemporal_snapshot_separates_observed_time_from_valid_time(tmp_path):
    store = WorldStore(str(tmp_path / "world.sqlite3"))
    store.append_event(
        "tenant-a",
        _fact(90_000, valid_from=50),
        observed_at=100,
    )
    store.append_event(
        "tenant-a",
        _fact(95_000, evidence_ids=["ev_2"], valid_from=180),
        observed_at=200,
    )

    historical = store.snapshot("tenant-a", observed_at=150, valid_at=120)
    assert historical["state_count"] == 1
    assert historical["states"][0]["effective"]["value"] == 90_000

    later_knowledge_about_old_valid_time = store.snapshot(
        "tenant-a",
        observed_at=250,
        valid_at=120,
    )
    assert later_knowledge_about_old_valid_time["states"][0]["effective"]["value"] == 90_000

    current = store.snapshot("tenant-a", observed_at=250, valid_at=220)
    assert current["states"][0]["effective"]["value"] == 95_000


def test_claim_fact_belief_are_kept_separate_and_conflicts_are_visible(tmp_path):
    store = WorldStore(str(tmp_path / "world.sqlite3"))
    first = WorldEventCreate(
        entity_id="company-x",
        entity_type="company",
        predicate="acquisition_target",
        value="Company Y",
        statement_kind="claim",
        confidence=0.72,
        source_ids=["source-a"],
    )
    second = first.model_copy(update={"value": "Company Z", "source_ids": ["source-b"]})
    belief = first.model_copy(
        update={
            "value": "Company Y",
            "statement_kind": "belief",
            "confidence": 0.61,
            "source_ids": [],
        }
    )
    store.append_event("tenant-a", first, observed_at=100)
    store.append_event("tenant-a", second, observed_at=110)
    store.append_event("tenant-a", belief, observed_at=120)

    state = store.snapshot("tenant-a", observed_at=130, valid_at=130)["states"][0]
    assert state["truth_status"] == "contested"
    assert len(state["claims"]) == 2
    assert state["fact"] is None
    assert state["belief"]["value"] == "Company Y"

    store.append_event(
        "tenant-a",
        _fact(
            "Company Y",
            entity_id="company-x",
            entity_type="company",
            entity_label="Company X",
            predicate="acquisition_target",
            evidence_ids=["official-filing"],
        ),
        observed_at=140,
    )
    resolved = store.snapshot("tenant-a", observed_at=150, valid_at=150)["states"][0]
    assert resolved["truth_status"] == "verified_disputed"
    assert resolved["fact"]["value"] == "Company Y"


def test_world_fork_freezes_parent_and_keeps_reality_unchanged(tmp_path):
    store = WorldStore(str(tmp_path / "world.sqlite3"))
    store.append_event(
        "tenant-a",
        _fact(30, entity_id="tr-policy", entity_type="macro", predicate="rate_pct"),
        observed_at=900,
    )
    branch = store.create_fork(
        "tenant-a",
        WorldForkCreate(
            name="Rate cut scenario",
            hypothesis="Policy rate falls by five percentage points",
            fork_observed_at=1000,
        ),
    )
    store.append_event(
        "tenant-a",
        _fact(
            32,
            entity_id="tr-policy",
            entity_type="macro",
            predicate="rate_pct",
            evidence_ids=["ev_reality_2"],
        ),
        observed_at=1100,
    )
    store.append_event(
        "tenant-a",
        WorldEventCreate(
            entity_id="tr-policy",
            entity_type="macro",
            predicate="rate_pct",
            value=25,
            statement_kind="assumption",
            confidence=1.0,
            branch_id=branch["id"],
        ),
        observed_at=1200,
    )

    reality = store.snapshot("tenant-a", observed_at=1300, valid_at=1300)
    forked = store.snapshot(
        "tenant-a",
        branch_id=branch["id"],
        observed_at=1300,
        valid_at=1300,
    )
    assert reality["states"][0]["effective"]["value"] == 32
    assert reality["states"][0]["truth_status"] == "verified"
    assert forked["states"][0]["effective"]["value"] == 25
    assert forked["states"][0]["truth_status"] == "hypothetical"

    diff = store.diff(
        "tenant-a",
        left_branch_id=REALITY_BRANCH,
        right_branch_id=branch["id"],
        observed_at=1300,
        valid_at=1300,
    )
    assert diff["change_count"] == 1


def test_reality_graph_builds_edges_from_entity_relations(tmp_path):
    store = WorldStore(str(tmp_path / "world.sqlite3"))
    store.append_event(
        "tenant-a",
        WorldEventCreate(
            entity_id="company-a",
            entity_type="company",
            entity_label="Company A",
            predicate="acquired",
            value=True,
            statement_kind="fact",
            confidence=1.0,
            evidence_ids=["filing-1"],
            object_entity_id="company-b",
            object_entity_type="company",
            object_entity_label="Company B",
        ),
        observed_at=100,
    )

    graph = store.graph("tenant-a", observed_at=200, valid_at=200)
    assert {node["entity_id"] for node in graph["nodes"]} == {"company-a", "company-b"}
    assert graph["edges"] == [
        {
            "source": "company-a",
            "target": "company-b",
            "predicate": "acquired",
            "truth_status": "verified",
            "confidence": 1.0,
            "event_id": graph["edges"][0]["event_id"],
        }
    ]


def test_world_pulse_and_tenant_isolation(tmp_path):
    store = WorldStore(str(tmp_path / "world.sqlite3"))
    event = WorldEventCreate(
        entity_id="btc",
        entity_type="crypto",
        predicate="signal",
        value="changed",
        statement_kind="claim",
        confidence=0.8,
    )
    for observed_at in (175, 180, 190):
        store.append_event("tenant-a", event, observed_at=observed_at)

    pulse = store.pulse("tenant-a", window_seconds=100, now=200)
    assert pulse["unusual"] is True
    assert pulse["categories"][0]["entity_type"] == "crypto"
    assert pulse["categories"][0]["current_count"] == 3

    assert store.snapshot("tenant-b", observed_at=200, valid_at=200)["state_count"] == 0
