from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.api import app
from app.agent_store import AGENT_STORE
from app.autonomy_store import AUTONOMY_STORE
from app.continual_generalist_v16 import (
    CONTINUAL_V16,
    SkillExperience,
    SkillPromotionPolicy,
    SkillCurriculumRequest,
    WorldFactCreate,
    WorldFactQuery,
)

HEADERS = {"X-API-Key": "test-secret"}


def wid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def experience(skill_id: str, task_id: str, domain: str, *, success: bool = True, safe: bool = True, novelty: float = 0.7) -> SkillExperience:
    return SkillExperience(
        task_id=task_id,
        skill_id=skill_id,
        domain=domain,
        success=success,
        evidence_coverage=0.95,
        confidence=0.90,
        regression_safe=safe,
        novelty=novelty,
        source_refs=[f"evidence:{task_id}"],
    )


def test_cross_domain_skill_promotion_requires_repeated_evidence() -> None:
    workspace = wid("promotion")
    skill_id = "skill-transfer"
    policy = SkillPromotionPolicy()

    for index in range(4):
        CONTINUAL_V16.record_experience(
            workspace,
            experience(skill_id, f"task-{index}", "engineering" if index < 2 else "operations"),
        )

    early = CONTINUAL_V16.evaluate_promotion(workspace, skill_id, policy)
    assert early.eligible is False
    assert "insufficient_observations" in early.reasons

    CONTINUAL_V16.record_experience(workspace, experience(skill_id, "task-4", "operations"))
    ready = CONTINUAL_V16.evaluate_promotion(workspace, skill_id, policy)

    assert ready.eligible is True
    assert ready.observations == 5
    assert ready.domains == ["engineering", "operations"]
    assert ready.success_rate == 1.0
    assert ready.regression_safe_rate == 1.0
    assert ready.high_novelty_successes == 5
    assert len(ready.decision_sha256) == 64


def test_regression_unsafe_experience_blocks_skill_promotion() -> None:
    workspace = wid("regression")
    skill_id = "skill-unsafe"
    for index in range(5):
        CONTINUAL_V16.record_experience(
            workspace,
            experience(
                skill_id,
                f"task-{index}",
                "engineering" if index < 3 else "finance",
                safe=index != 4,
            ),
        )

    decision = CONTINUAL_V16.evaluate_promotion(workspace, skill_id, SkillPromotionPolicy())
    assert decision.eligible is False
    assert "regression_safety_below_threshold" in decision.reasons


def test_world_model_is_temporal_evidence_bound_and_detects_conflicts() -> None:
    workspace = wid("world")
    first = CONTINUAL_V16.add_fact(
        workspace,
        WorldFactCreate(
            subject="machine-1",
            predicate="operating_state",
            value={"state": "idle"},
            domain="industrial",
            confidence=0.95,
            evidence_refs=["sensor:a"],
            observed_at=100,
            valid_from=100,
            valid_to=199,
        ),
    )
    second = CONTINUAL_V16.add_fact(
        workspace,
        WorldFactCreate(
            subject="machine-1",
            predicate="operating_state",
            value={"state": "running"},
            domain="industrial",
            confidence=0.96,
            evidence_refs=["sensor:b"],
            observed_at=200,
            valid_from=200,
            valid_to=400,
        ),
    )

    at_150 = CONTINUAL_V16.query_facts(
        workspace,
        WorldFactQuery(subject="machine-1", predicate="operating_state", valid_at=150),
    )
    assert [fact.fact_id for fact in at_150.facts] == [first.fact_id]
    assert at_150.contradiction_detected is False

    at_250 = CONTINUAL_V16.query_facts(
        workspace,
        WorldFactQuery(subject="machine-1", predicate="operating_state", valid_at=250),
    )
    assert [fact.fact_id for fact in at_250.facts] == [second.fact_id]
    assert at_250.contradiction_detected is False

    all_history = CONTINUAL_V16.query_facts(
        workspace,
        WorldFactQuery(subject="machine-1", predicate="operating_state"),
    )
    assert len(all_history.facts) == 2
    assert all_history.contradiction_detected is True


def test_world_model_is_workspace_isolated() -> None:
    owner = wid("owner")
    other = wid("other")
    CONTINUAL_V16.add_fact(
        owner,
        WorldFactCreate(
            subject="asset-x",
            predicate="temperature",
            value=42,
            domain="engineering",
            confidence=1.0,
            evidence_refs=["measurement:1"],
        ),
    )

    result = CONTINUAL_V16.query_facts(other, WorldFactQuery(subject="asset-x"))
    assert result.facts == []


def test_api_can_promote_only_after_learning_gate_passes() -> None:
    client = TestClient(app)
    workspace = wid("api")
    headers = {**HEADERS, "X-Workspace-ID": workspace}
    skill_id = "learned-analysis"

    for index in range(5):
        response = client.post(
            "/v16/continual/skills/experiences",
            headers=headers,
            json={
                "task_id": f"api-task-{index}",
                "skill_id": skill_id,
                "domain": "engineering" if index < 3 else "operations",
                "success": True,
                "evidence_coverage": 0.95,
                "confidence": 0.9,
                "regression_safe": True,
                "novelty": 0.75,
                "source_refs": [f"case:{index}"],
            },
        )
        assert response.status_code == 200

    decision = client.post(
        f"/v16/continual/skills/{skill_id}/promotion",
        headers=headers,
        json={},
    )
    assert decision.status_code == 200
    assert decision.json()["eligible"] is True

    promote = client.post(
        f"/v16/continual/skills/{skill_id}/promote",
        headers=headers,
        json={
            "skill": {
                "skill_id": skill_id,
                "display_name": "Learned Analysis",
                "version": "1.0.0",
                "description": "Evidence-gated learned cross-domain analysis procedure.",
                "capabilities": ["analysis"],
                "required_tool_ids": [],
                "risk_tier": "moderate",
                "enabled": True,
            },
            "policy": {},
        },
    )
    assert promote.status_code == 200
    stored = {item["skill_id"]: item for item in AUTONOMY_STORE.list_skills(workspace)}
    assert skill_id in stored
    assert stored[skill_id]["enabled"] is True


def test_v16_readiness_explicitly_does_not_claim_agi() -> None:
    client = TestClient(app)
    workspace = wid("readiness")
    response = client.get("/v16/continual/readiness", headers={**HEADERS, "X-Workspace-ID": workspace})
    assert response.status_code == 200
    payload = response.json()
    assert payload["persistent_experience_memory"] is True
    assert payload["cross_domain_skill_promotion"] is True
    assert payload["temporal_evidence_bound_world_model"] is True
    assert payload["model_weight_learning"] is False
    assert payload["live_agi_claim"] is False
    assert "not proof of AGI" in payload["boundary"]


def test_curriculum_targets_unseen_and_underperforming_domains() -> None:
    workspace = wid("curriculum")
    skill_id = "skill-curriculum"
    for index in range(3):
        CONTINUAL_V16.record_experience(
            workspace,
            SkillExperience(
                task_id=f"cur-task-{index}",
                skill_id=skill_id,
                domain="engineering",
                success=index > 0,
                evidence_coverage=0.60,
                confidence=0.70,
                regression_safe=True,
                novelty=0.50,
                source_refs=[f"case:{index}"],
            ),
        )

    plan = CONTINUAL_V16.build_curriculum(
        workspace,
        skill_id,
        SkillCurriculumRequest(target_domains=["engineering", "finance", "operations"]),
    )

    assert plan.gap_domains == ["engineering", "finance", "operations"]
    by_domain = {task.domain: task for task in plan.tasks}
    assert by_domain["finance"].existing_observations == 0
    assert by_domain["operations"].recommended_novelty == 0.75
    assert "domain_evidence_below_target" in by_domain["engineering"].reason_codes
    assert len(plan.plan_sha256) == 64


def test_verified_world_fact_consolidates_into_agent_semantic_memory() -> None:
    client = TestClient(app)
    workspace = wid("consolidate")
    agent_id = "agent-v16"
    headers = {**HEADERS, "X-Workspace-ID": workspace}
    AGENT_STORE.upsert_agent(workspace, {"agent_id": agent_id, "enabled": True})

    created = client.post(
        "/v16/continual/world/facts",
        headers=headers,
        json={
            "subject": "line-a",
            "predicate": "nominal_pressure",
            "value": {"bar": 8.5},
            "domain": "engineering",
            "confidence": 0.97,
            "evidence_refs": ["sensor:pressure:001"],
            "observed_at": 1000,
            "valid_from": 900,
            "valid_to": 2000,
        },
    )
    assert created.status_code == 200

    consolidated = client.post(
        "/v16/continual/world/consolidate-memory",
        headers=headers,
        json={
            "agent_id": agent_id,
            "subject": "line-a",
            "predicate": "nominal_pressure",
            "domain": "engineering",
            "valid_at": 1500,
            "minimum_confidence": 0.9,
        },
    )
    assert consolidated.status_code == 200
    payload = consolidated.json()
    memories = AUTONOMY_STORE.query_memories(
        workspace,
        agent_id=agent_id,
        kinds=["semantic"],
        tags=[],
        min_confidence=0.9,
        limit=20,
    )
    assert any(memory["memory_id"] == payload["memory_id"] for memory in memories)
    memory = next(memory for memory in memories if memory["memory_id"] == payload["memory_id"])
    assert memory["content"]["source"] == "world_model_v16"
    assert memory["content"]["value"] == {"bar": 8.5}
    assert "sensor:pressure:001" in memory["source_refs"]
