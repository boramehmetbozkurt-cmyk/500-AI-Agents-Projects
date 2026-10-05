from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text

from app import PLATFORM_RELEASE, __version__
from app.adaptive_store import ADAPTIVE_STORE
from app.agent_store import AGENT_STORE
from app.autonomy_store import AUTONOMY_STORE
from app.config import SETTINGS
from app.enterprise_store import ENTERPRISE_STORE
from app.security import Principal, require_minimum_role
from app.store import STORE

router = APIRouter(prefix="/v1/system", tags=["system"])
_REQUIRE_EVALUATOR = require_minimum_role("evaluator")


def _canonical(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, default=str)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


@router.get("/version")
def version() -> dict[str, object]:
    return {
        "product": "ORBYTHRA",
        "version": __version__,
        "api_major": 1,
        "latest_api_major": 4,
        "supported_api_majors": [1, 2, 3, 4],
        "platform_release": PLATFORM_RELEASE,
        "release_sha": SETTINGS.release_sha,
        "platform_capabilities": ["v21_assurance_lab", "w3c_trace_context", "otlp_http_json", "versioned_eval_datasets", "versioned_prompts", "reproducible_experiments", "trace_assurance_lineage", "v22_crypto_hardening", "isolated_signing_roots", "hybrid_mldsa65_signatures", "hybrid_mlkem768_x25519_recipient_protection", "mandatory_production_replay_defense", "v23_verifiable_general_agent", "v23_1_keyless_web_research", "v23_1_workspace_attachments", "v23_2_agent_context_snapshots", "v23_2_goal_lifecycle", "v23_2_chained_cycle_receipts", "v23_2_receipt_verification"],
        "deployment_id": SETTINGS.deployment_id,
        "claim": "Version metadata only; deployment, agentic/autonomy/adaptive safety, general-intelligence and external-validation claims require their own evidence.",
    }


@router.get("/assurance-manifest")
def assurance_manifest(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> dict[str, object]:
    providers = ENTERPRISE_STORE.list_providers(principal.workspace_id)
    identities = ENTERPRISE_STORE.list_identities(principal.workspace_id)
    benchmarks = ENTERPRISE_STORE.list_benchmarks(principal.workspace_id, 100)
    usage = ENTERPRISE_STORE.usage_report(principal.workspace_id)
    audits = STORE.recent_audit(principal.workspace_id, 200)
    agents = AGENT_STORE.list_agents(principal.workspace_id)
    tools = AGENT_STORE.list_tools(principal.workspace_id)
    skills = AUTONOMY_STORE.list_skills(principal.workspace_id)
    strategies = ADAPTIVE_STORE.list_strategies(principal.workspace_id)

    with ENTERPRISE_STORE.engine.connect() as conn:
        rows = conn.execute(
            text("SELECT DISTINCT policy_id FROM enterprise_policy_revisions WHERE workspace_id=:workspace_id ORDER BY policy_id"),
            {"workspace_id": principal.workspace_id},
        ).all()
    policy_ids = [str(row[0]) for row in rows]
    policy_history = {policy_id: ENTERPRISE_STORE.policy_history(principal.workspace_id, policy_id) for policy_id in policy_ids}

    with ADAPTIVE_STORE.engine.connect() as conn:
        world_rows = [dict(row) for row in conn.execute(
            text("SELECT agent_id,domain,revision,state_sha256,previous_sha256,created_at FROM adaptive_world_state WHERE workspace_id=:workspace_id ORDER BY agent_id,domain,revision"),
            {"workspace_id": principal.workspace_id},
        ).mappings().all()]
        learning_rows = [dict(row) for row in conn.execute(
            text("SELECT learning_id,revision,status,learning_sha256,previous_sha256,created_at FROM adaptive_learning WHERE workspace_id=:workspace_id ORDER BY learning_id,revision"),
            {"workspace_id": principal.workspace_id},
        ).mappings().all()]
        transfer_rows = [dict(row) for row in conn.execute(
            text("SELECT transfer_id,transfer_sha256,created_at FROM adaptive_transfers WHERE workspace_id=:workspace_id ORDER BY transfer_id"),
            {"workspace_id": principal.workspace_id},
        ).mappings().all()]

    audit_projection = [
        {"event_id": item.get("event_id"), "request_id": item.get("request_id"), "action": item.get("action"), "status": item.get("status"), "created_at": item.get("created_at")}
        for item in audits
    ]
    identity_projection = [
        {"subject_hash": hashlib.sha256(str(item.get("subject", "")).encode("utf-8")).hexdigest(), "active": bool(item.get("active")), "role_override": item.get("role_override"), "updated_at": item.get("updated_at")}
        for item in identities
    ]
    agent_projection = [
        {
            "agent_id": item.get("agent_id"),
            "enabled": item.get("enabled"),
            "allowed_tool_ids": item.get("allowed_tool_ids"),
            "max_risk_tier": item.get("max_risk_tier"),
            "human_approval_from_risk": item.get("human_approval_from_risk"),
            "signed_approval_from_risk": item.get("signed_approval_from_risk"),
            "supervisor_agent_id": item.get("supervisor_agent_id"),
            "updated_at": item.get("updated_at"),
        }
        for item in agents
    ]
    tool_projection = [
        {
            "tool_id": item.get("tool_id"),
            "protocol": item.get("protocol"),
            "allowed_operations": item.get("allowed_operations"),
            "risk_tier": item.get("risk_tier"),
            "writes_state": item.get("writes_state"),
            "requires_idempotency_key": item.get("requires_idempotency_key"),
            "enabled": item.get("enabled"),
            "updated_at": item.get("updated_at"),
        }
        for item in tools
    ]
    skill_projection = [
        {
            "skill_id": item.get("skill_id"),
            "version": item.get("version"),
            "capabilities": item.get("capabilities"),
            "required_tool_ids": item.get("required_tool_ids"),
            "risk_tier": item.get("risk_tier"),
            "enabled": item.get("enabled"),
            "updated_at": item.get("updated_at"),
        }
        for item in skills
    ]
    strategy_projection = [
        {
            "strategy_id": item.get("strategy_id"),
            "domains": item.get("domains"),
            "capabilities": item.get("capabilities"),
            "risk_tier": item.get("risk_tier"),
            "provider_id": item.get("provider_id"),
            "success_score": item.get("success_score"),
            "latency_score": item.get("latency_score"),
            "cost_score": item.get("cost_score"),
            "enabled": item.get("enabled"),
            "updated_at": item.get("updated_at"),
        }
        for item in strategies
    ]

    body: dict[str, object] = {
        "product": "ORBYTHRA",
        "version": __version__,
        "workspace_id": principal.workspace_id,
        "generated_at": int(time.time()),
        "release_identity": {
            "release_sha": SETTINGS.release_sha,
            "deployment_id": SETTINGS.deployment_id,
            "environment": SETTINGS.environment,
            "database_backend": STORE.backend,
            "key_management_mode": SETTINGS.key_management_mode,
            "signing_keys_isolated": SETTINGS.signing_keys_isolated,
            "pqc_mode": SETTINGS.pqc_mode,
        },
        "evidence": {
            "provider_count": len(providers),
            "provider_registry_sha256": _hash(providers),
            "policy_count": len(policy_history),
            "policy_history_sha256": _hash(policy_history),
            "identity_count": len(identities),
            "identity_registry_sha256": _hash(identity_projection),
            "benchmark_count": len(benchmarks),
            "benchmark_history_sha256": _hash(benchmarks),
            "usage_report": usage,
            "audit_event_count_sampled": len(audit_projection),
            "audit_projection_sha256": _hash(audit_projection),
            "agent_count": len(agent_projection),
            "agent_registry_sha256": _hash(agent_projection),
            "tool_count": len(tool_projection),
            "tool_registry_sha256": _hash(tool_projection),
            "skill_count": len(skill_projection),
            "skill_registry_sha256": _hash(skill_projection),
            "adaptive_world_state_revision_count": len(world_rows),
            "adaptive_world_state_sha256": _hash(world_rows),
            "adaptive_learning_revision_count": len(learning_rows),
            "adaptive_learning_history_sha256": _hash(learning_rows),
            "adaptive_strategy_count": len(strategy_projection),
            "adaptive_strategy_registry_sha256": _hash(strategy_projection),
            "adaptive_transfer_proposal_count": len(transfer_rows),
            "adaptive_transfer_registry_sha256": _hash(transfer_rows),
        },
        "external_gates": {
            "independent_penetration_test": "PENDING_EXTERNAL_PARTY",
            "independent_cryptographic_review": "PENDING_EXTERNAL_PARTY",
            "independent_product_validation": "PENDING_EXTERNAL_PARTY",
            "independent_agentic_security_validation": "PENDING_EXTERNAL_PARTY",
            "independent_autonomy_validation": "PENDING_EXTERNAL_PARTY",
            "independent_adaptive_generalist_validation": "PENDING_EXTERNAL_PARTY",
            "real_mcp_interoperability": "PENDING_INTEGRATION_TESTS",
            "live_autonomous_production_history": "PENDING_PRODUCTION_OPERATION",
            "foundation_model_weight_self_training": "NOT_IMPLEMENTED_OR_CLAIMED",
            "general_intelligence_or_agi_evidence": "NOT_CLAIMED",
            "paid_enterprise_customer_evidence": "PENDING_COMMERCIAL_EXECUTION",
            "recurring_revenue_evidence": "PENDING_COMMERCIAL_EXECUTION",
            "formal_soc2_iso27001": "PENDING_FORMAL_AUDIT",
        },
        "validation_boundary": "This manifest hashes internal technical, agentic-control, bounded-autonomy and application-level adaptive-learning evidence. It is not independent certification, autonomous/adaptive-system safety certification, foundation-model self-training evidence, an AGI claim, a legal compliance opinion, revenue proof or customer acceptance.",
    }
    body["manifest_sha256"] = _hash(body)
    return body
