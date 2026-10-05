from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

import app.planner_synthesis_v19 as synthmod
from app.agent_store import AGENT_STORE
from app.api import app
from app.autonomy_store import AUTONOMY_STORE
from app.continual_generalist_v16 import CONTINUAL_V16, WorldFactCreate
from app.failure_memory_v15 import FAILURE_MEMORY_V15, FailureObservation
from app.hierarchical_generalist_v17 import GoalCheckpointRequest, ProgramCreate, V17
from app.planner_reflection_v19 import ReflectionRequest, assess_program
from app.planner_synthesis_v19 import PLANNER_V19, PlannerSynthesisRequest

HEADERS = {"X-API-Key": "test-secret"}


def wid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def create_program(workspace: str):
    AGENT_STORE.upsert_agent(
        workspace,
        {
            "agent_id": "agent-v19",
            "enabled": True,
            "max_risk_tier": "high",
            "allowed_tool_ids": [],
        },
    )
    return V17.create_program(
        workspace,
        ProgramCreate(
            agent_id="agent-v19",
            objective="Deliver a verified cross-domain analysis",
            success_criteria=["final evidence verified"],
            constraints=["no unverified claims"],
            risk_budget="high",
            maximum_depth=4,
            maximum_nodes=20,
            maximum_actions=50,
        ),
    )


def test_planner_uses_metadata_only_and_applies_validated_subgoals(monkeypatch) -> None:
    workspace = wid("planner")
    program = create_program(workspace)

    AUTONOMY_STORE.add_memory(
        workspace,
        {
            "agent_id": "agent-v19",
            "kind": "semantic",
            "content": {"secret": "TOP-SECRET-MEMORY-CONTENT"},
            "tags": ["planning", "private"],
            "confidence": 0.9,
            "source_refs": ["memory-source"],
            "sensitivity": "restricted",
            "ttl_seconds": None,
        },
    )
    CONTINUAL_V16.add_fact(
        workspace,
        WorldFactCreate(
            subject="asset-1",
            predicate="hidden_value",
            value="TOP-SECRET-WORLD-VALUE",
            domain="engineering",
            confidence=0.95,
            evidence_refs=["sensor:1"],
        ),
    )

    captured = {}

    def fake_generate(self, *, model_id: str, prompt: str):
        captured["prompt"] = prompt
        return {
            "output": """{"rationale":"decompose into evidence and verification","subgoals":[{"objective":"Collect evidence","success_criteria":["evidence collected"],"required_capabilities":["retrieval"],"constraints":["use traceable sources"],"risk_tier":"moderate","priority":0.9,"maximum_attempts":4},{"objective":"Verify evidence","success_criteria":["evidence verified"],"required_capabilities":["verification"],"constraints":["reject unsupported claims"],"risk_tier":"moderate","priority":0.8,"maximum_attempts":4}]}""",
            "confidence": 0.9,
            "provider_response_sha256": "f" * 64,
        }

    monkeypatch.setattr(synthmod.GovernedHttpModelAdapter, "generate", fake_generate)

    proposal = PLANNER_V19.synthesize(
        workspace,
        PlannerSynthesisRequest(
            program_id=program.program_id,
            goal_id=program.root_goal_id,
            model_id="planner-model",
            maximum_subgoals=4,
        ),
    )
    assert len(proposal.subgoals) == 2
    assert "TOP-SECRET-MEMORY-CONTENT" not in captured["prompt"]
    assert "TOP-SECRET-WORLD-VALUE" not in captured["prompt"]
    assert "memory-source" not in captured["prompt"]
    assert "sensor:1" not in captured["prompt"]
    assert "asset-1" in captured["prompt"]
    assert "planning" in captured["prompt"]

    goals = PLANNER_V19.apply(workspace, proposal.proposal_id)
    assert len(goals) == 2
    assert {goal.objective for goal in goals} == {"Collect evidence", "Verify evidence"}

    stored = PLANNER_V19.get(workspace, proposal.proposal_id)
    assert stored is not None
    assert stored.applied is True


def test_planner_rejects_subgoal_above_risk_budget(monkeypatch) -> None:
    workspace = wid("risk")
    program = create_program(workspace)

    def fake_generate(self, *, model_id: str, prompt: str):
        return {
            "output": """{"rationale":"unsafe proposal","subgoals":[{"objective":"Critical intervention","success_criteria":["intervention complete"],"required_capabilities":[],"constraints":[],"risk_tier":"critical","priority":1.0,"maximum_attempts":2}]}""",
            "confidence": 0.9,
            "provider_response_sha256": "e" * 64,
        }

    monkeypatch.setattr(synthmod.GovernedHttpModelAdapter, "generate", fake_generate)

    try:
        PLANNER_V19.synthesize(
            workspace,
            PlannerSynthesisRequest(
                program_id=program.program_id,
                goal_id=program.root_goal_id,
                model_id="planner-model",
            ),
        )
        assert False, "expected risk rejection"
    except ValueError as exc:
        assert str(exc) == "planner_subgoal_risk_exceeds_budget"


def test_reflection_replans_on_distribution_shift() -> None:
    workspace = wid("reflect")
    program = create_program(workspace)

    result = assess_program(
        workspace,
        ReflectionRequest(
            program_id=program.program_id,
            confidence=0.8,
            evidence_coverage=0.9,
            contradiction_rate=0.0,
            recent_failure_rate=0.0,
            distribution_shift=0.5,
        ),
    )
    assert result.action == "REPLAN"
    assert "metacognitive_strategy_change_required" in result.reason_codes
    assert result.release_blocked is False


def test_reflection_blocks_when_failure_memory_has_high_open_failure() -> None:
    workspace = wid("block")
    program = create_program(workspace)

    V17.checkpoint(
        workspace,
        program.root_goal_id,
        GoalCheckpointRequest(
            observations=[{"result": "final evidence verified"}],
            criterion_results={"final evidence verified": True},
            evidence_refs=["report:complete"],
        ),
    )
    assert V17.evaluate_goal(workspace, program.root_goal_id).status == "COMPLETE"

    FAILURE_MEMORY_V15.record(
        workspace,
        FailureObservation(
            component="planner-v19",
            error_class="unsafe-generalization",
            invariant="high-risk unsafe generalization must block continuation",
            severity="high",
            evidence_sha256="a" * 64,
            release_sha="abcdefg",
        ),
        now=1000,
    )

    result = assess_program(
        workspace,
        ReflectionRequest(
            program_id=program.program_id,
            confidence=0.9,
            evidence_coverage=0.9,
            contradiction_rate=0.0,
            recent_failure_rate=0.0,
            distribution_shift=0.0,
        ),
    )
    assert result.action == "BLOCK"
    assert result.release_blocked is True
    assert "high_or_critical_failure_memory_block" in result.reason_codes


def test_v19_readiness_preserves_authority_boundary() -> None:
    client = TestClient(app)
    workspace = wid("readiness")
    response = client.get("/v19/reflection/readiness", headers={**HEADERS, "X-Workspace-ID": workspace})
    assert response.status_code == 200
    payload = response.json()
    assert payload["structured_model_plan_synthesis"] is True
    assert payload["metadata_only_private_context"] is True
    assert payload["automatic_tool_execution"] is False
    assert payload["permission_self_escalation"] is False
    assert payload["live_agi_claim"] is False
    assert "not proof of AGI" in payload["boundary"]
