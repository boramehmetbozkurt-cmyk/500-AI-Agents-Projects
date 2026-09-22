from __future__ import annotations

from enterprise_readiness import (
    EnterpriseProofStore,
    FingerprintRequest,
    PilotCreate,
    PilotMetricUpdate,
    knowledge_fingerprint,
    product_readiness_scorecard,
)


def test_internal_product_dimensions_are_above_nine() -> None:
    scorecard = product_readiness_scorecard()
    scores = [float(item["score"]) for item in scorecard["dimensions"].values()]
    assert scores
    assert min(scores) >= 9.0
    assert scorecard["external_proof"]["numeric_score"] is None
    assert scorecard["external_proof"]["not_fabricated"] is True


def test_knowledge_fingerprint_is_stable_and_evidence_sensitive() -> None:
    base = FingerprintRequest(
        query="Where did this event happen?",
        report={"claims": [{"text": "A", "evidence_ids": ["ev1"]}]},
        evidence_index=[{"provider": "alpha", "url": "https://example.com/a"}],
        receipt={"evidence_digest": "one"},
    )
    first = knowledge_fingerprint(base)
    second = knowledge_fingerprint(base)
    assert first["fingerprint"] == second["fingerprint"]

    changed = base.model_copy(
        update={
            "evidence_index": [
                {"provider": "beta", "url": "https://example.com/b"}
            ]
        }
    )
    assert knowledge_fingerprint(changed)["fingerprint"] != first["fingerprint"]


def test_pilot_metrics_are_tenant_isolated_and_measured(tmp_path) -> None:
    store = EnterpriseProofStore(str(tmp_path / "enterprise.sqlite3"))
    pilot = store.create(
        "tenant-a",
        PilotCreate(
            name="Research pilot",
            use_case="Measure grounded research task quality",
            target_tasks=20,
        ),
    )
    assert pilot["evidence_status"] == "awaiting-real-pilot-data"

    updated = store.update_metrics(
        "tenant-a",
        pilot["id"],
        PilotMetricUpdate(
            completed_tasks=10,
            task_success_rate=0.92,
            grounded_claim_rate=0.96,
            human_acceptance_rate=0.9,
            median_latency_seconds=18.0,
            cost_per_task_usd=0.42,
        ),
    )
    assert updated["completion_ratio"] == 0.5
    assert updated["evidence_status"] == "self-reported-unverified"
    assert "user-entered" in updated["evidence_note"]
    assert updated["quality_index"] == 0.9267
    assert store.list("tenant-b") == []
