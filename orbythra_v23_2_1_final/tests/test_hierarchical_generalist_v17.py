from __future__ import annotations

import uuid
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.hierarchical_generalist_v17 as v17mod
from app.agent_store import AGENT_STORE
from app.api import app
from app.autonomy_store import AUTONOMY_STORE
from app.causal_intelligence_v11 import CausalRequest
from app.continual_generalist_v16 import CONTINUAL_V16, SkillExperience
from app.hierarchical_generalist_v17 import (
    CounterfactualImpactRequest,
    GoalCheckpointRequest,
    GoalExpansionRequest,
    GoalReplanRequest,
    GoalSpec,
    HierarchicalGeneralistV17,
    ProgramCreate,
    SkillCandidatePromotionRequest,
    SkillTraceSynthesisRequest,
    SkillTrialRequest,
    V17,
    VerifiedCausalModelRequest,
)

HEADERS = {"X-API-Key": "test-secret"}


def wid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def register_agent(workspace: str, agent_id: str = "agent-v17") -> None:
    AGENT_STORE.upsert_agent(
        workspace,
        {
            "agent_id": agent_id,
            "enabled": True,
            "max_risk_tier": "high",
            "allowed_tool_ids": [],
        },
    )


def test_hierarchical_program_completes_and_survives_store_restart() -> None:
    workspace = wid("hierarchy")
    register_agent(workspace)
    program = V17.create_program(
        workspace,
        ProgramCreate(
            agent_id="agent-v17",
            objective="Deliver verified engineering review",
            success_criteria=["root verified"],
            constraints=["evidence required"],
            risk_budget="high",
            maximum_depth=4,
            maximum_nodes=20,
            maximum_actions=50,
        ),
    )
    children = V17.expand_goal(
        workspace,
        program.root_goal_id,
        GoalExpansionRequest(
            subgoals=[
                GoalSpec(
                    objective="Collect evidence",
                    success_criteria=["evidence collected"],
                    priority=0.9,
                ),
                GoalSpec(
                    objective="Verify claims",
                    success_criteria=["claims verified"],
                    priority=0.8,
                ),
            ]
        ),
    )

    state = V17.resume_state(workspace, program.program_id)
    assert state.next_goal is not None
    assert state.next_goal.goal_id == children[0].goal_id
    assert state.completion_ratio == 0.0

    for child, criterion in zip(children, ["evidence collected", "claims verified"]):
        checkpoint = V17.checkpoint(
            workspace,
            child.goal_id,
            GoalCheckpointRequest(
                observations=[{"result": criterion}],
                criterion_results={criterion: True},
                evidence_refs=[f"evidence:{child.goal_id}"],
            ),
        )
        assert checkpoint.status == "ACTIVE"
        evaluation = V17.evaluate_goal(workspace, child.goal_id)
        assert evaluation.status == "COMPLETE"

    V17.checkpoint(
        workspace,
        program.root_goal_id,
        GoalCheckpointRequest(
            observations=[{"result": "root verified"}],
            criterion_results={"root verified": True},
            evidence_refs=["report:final"],
        ),
    )
    root_eval = V17.evaluate_goal(workspace, program.root_goal_id)
    assert root_eval.status == "COMPLETE"

    restarted = HierarchicalGeneralistV17()
    restored = restarted.resume_state(workspace, program.program_id)
    assert restored.program.status == "COMPLETE"
    assert restored.next_goal is None
    assert restored.completion_ratio == 1.0


def test_replan_supersedes_incomplete_branch_and_resumes_replacement() -> None:
    workspace = wid("replan")
    register_agent(workspace)
    program = V17.create_program(
        workspace,
        ProgramCreate(
            agent_id="agent-v17",
            objective="Resolve difficult task",
            success_criteria=["resolved"],
            maximum_replans=3,
        ),
    )
    original = V17.expand_goal(
        workspace,
        program.root_goal_id,
        GoalExpansionRequest(
            subgoals=[
                GoalSpec(objective="Attempt path A", success_criteria=["path A works"], priority=0.9)
            ]
        ),
    )[0]

    replacements = V17.replan_goal(
        workspace,
        program.root_goal_id,
        GoalReplanRequest(
            reason="Path A did not produce sufficient evidence",
            replacement_subgoals=[
                GoalSpec(objective="Attempt path B", success_criteria=["path B works"], priority=1.0)
            ],
        ),
    )
    assert V17.get_goal(workspace, original.goal_id).status == "SUPERSEDED"
    state = V17.resume_state(workspace, program.program_id)
    assert state.next_goal is not None
    assert state.next_goal.goal_id == replacements[0].goal_id
    assert state.program.replans_used == 1


def test_candidate_cannot_borrow_unrelated_v16_history_to_bypass_trials() -> None:
    workspace = wid("candidate-bypass")
    skill_id = "candidate-isolated"

    for index in range(5):
        CONTINUAL_V16.record_experience(
            workspace,
            SkillExperience(
                task_id=f"legacy-{index}",
                skill_id=skill_id,
                domain="engineering" if index < 3 else "operations",
                success=True,
                evidence_coverage=1.0,
                confidence=1.0,
                regression_safe=True,
                novelty=0.9,
                source_refs=[f"legacy:{index}"],
            ),
        )

    candidate = V17.synthesize_candidate(
        workspace,
        SkillTraceSynthesisRequest(
            skill_id=skill_id,
            display_name="Candidate Isolated Skill",
            description="Must earn its own trial evidence.",
            source_task_ids=["source-1", "source-2"],
            domains=["engineering"],
            procedure_steps=["inspect", "verify"],
            capabilities=["analysis"],
            required_tool_ids=[],
            risk_tier="moderate",
            evidence_refs=["trace:1"],
        ),
    )
    decision = V17.candidate_decision(workspace, candidate.candidate_id, v17mod.SkillPromotionPolicy())
    assert decision.status == "CANDIDATE"
    assert decision.v16_eligible is False
    assert "candidate_insufficient_trials" in decision.reasons


def test_trace_synthesized_skill_promotes_after_cross_domain_safe_trials() -> None:
    workspace = wid("skill")
    candidate = V17.synthesize_candidate(
        workspace,
        SkillTraceSynthesisRequest(
            skill_id="trace-analysis",
            display_name="Trace Analysis",
            description="Reusable analysis procedure synthesized from successful traces.",
            source_task_ids=["source-a", "source-b"],
            domains=["engineering", "operations"],
            procedure_steps=["decompose", "retrieve evidence", "verify", "record outcome"],
            capabilities=["analysis", "verification"],
            required_tool_ids=[],
            risk_tier="moderate",
            evidence_refs=["trace:a", "trace:b"],
        ),
    )

    final = None
    for index in range(5):
        final = V17.record_trial(
            workspace,
            candidate.candidate_id,
            SkillTrialRequest(
                task_id=f"trial-{index}",
                domain="engineering" if index < 3 else "operations",
                success=True,
                evidence_coverage=0.95,
                confidence=0.9,
                regression_safe=True,
                novelty=0.75,
                evidence_refs=[f"trial-evidence:{index}"],
            ),
        )
    assert final is not None
    assert final.status == "PROMOTABLE"
    assert final.v16_eligible is True

    promoted = V17.promote_candidate(
        workspace,
        candidate.candidate_id,
        SkillCandidatePromotionRequest(version="1.0.0"),
    )
    assert promoted.skill_id == "trace-analysis"
    stored = {item["skill_id"]: item for item in AUTONOMY_STORE.list_skills(workspace)}
    assert stored["trace-analysis"]["enabled"] is True
    assert "decompose" in stored["trace-analysis"]["description"]


def test_verified_causal_graph_supports_bounded_counterfactual_reachability(monkeypatch) -> None:
    workspace = wid("causal")
    monkeypatch.setattr(
        v17mod,
        "evaluate_causal",
        lambda body, workspace_id: SimpleNamespace(
            status="PASS",
            graph_sha256="a" * 64,
            evidence_sha256="b" * 64,
        ),
    )
    request = CausalRequest(
        request_id="causal-v17-test",
        hypothesis="A affects downstream system state",
        edges=[
            {
                "cause": "A",
                "effect": "B",
                "mechanism": "A changes B",
                "evidence_claims": ["A changes B"],
                "confidence": 0.9,
                "confounders": ["C1"],
            },
            {
                "cause": "B",
                "effect": "D",
                "mechanism": "B changes D",
                "evidence_claims": ["B changes D"],
                "confidence": 0.9,
                "confounders": ["C2"],
            },
        ],
        evidence=[{"source_id": "source-1", "text": "Evidence supplied for causal hypothesis."}],
        intervention="set A",
        counterfactual="if A changed",
    )
    model = V17.register_causal_model(workspace, VerifiedCausalModelRequest(causal_request=request))
    result = V17.counterfactual_impact(
        workspace,
        model.model_id,
        CounterfactualImpactRequest(intervention_node="A", maximum_hops=4),
    )
    assert result.impacted_nodes == ["B", "D"]
    assert ["A", "B"] in result.paths
    assert ["A", "B", "D"] in result.paths
    assert "does not estimate intervention magnitude" in result.boundary
    assert len(result.result_sha256) == 64


def test_v17_api_readiness_and_claim_boundary() -> None:
    client = TestClient(app)
    workspace = wid("readiness")
    response = client.get("/v17/generalist/readiness", headers={**HEADERS, "X-Workspace-ID": workspace})
    assert response.status_code == 200
    payload = response.json()
    assert payload["persistent_hierarchical_programs"] is True
    assert payload["bounded_long_horizon_resume"] is True
    assert payload["trace_based_skill_synthesis"] is True
    assert payload["evidence_gated_causal_model"] is True
    assert payload["unrestricted_self_modification"] is False
    assert payload["model_weight_learning"] is False
    assert payload["live_agi_claim"] is False
    assert "does not prove AGI" in payload["boundary"]
