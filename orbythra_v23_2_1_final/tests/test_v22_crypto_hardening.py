from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

import app.agents as agents_module
import app.crypto_core as crypto_core
import app.main as main_module
from app.agent_models import AgentActionRequest, AgentProfile, ToolProfile
from app.agent_policy import evaluate_agent_policy
from app.config import SETTINGS
from app.crypto_core import (
    CryptoConfigurationError,
    CryptoValidationError,
    KeyRing,
    commitment,
    generate_hybrid_approval_keypair,
    generate_hybrid_recipient_keypair,
    open_envelope,
    pqc_backend_available,
    seal,
    sign_approval,
    sign_hybrid_approval,
    signature_input_for_envelope,
)
from app.crypto_recipient import open_hybrid_recipient_envelope
from app.api import app

client = TestClient(app)
HEADERS = {"X-API-Key": "test-secret", "X-Workspace-ID": "v22-lab"}


def _b64(byte: bytes) -> str:
    return crypto_core._b64e(byte * 32)


def _production_settings(*, pqc_mode: str = "off"):
    return replace(
        SETTINGS,
        environment="production",
        master_keys=(("enc-v22", _b64(b"e")),),
        signing_keys=(("sig-v22", _b64(b"s")),),
        allow_legacy_approvals=False,
        pqc_mode=pqc_mode,
    )


def _install_settings(monkeypatch, settings) -> None:
    monkeypatch.setattr(crypto_core, "SETTINGS", settings)
    monkeypatch.setattr(crypto_core, "KEYRING", KeyRing(settings.master_keys))


def test_production_rejects_opaque_legacy_approvals(monkeypatch):
    settings = _production_settings()
    _install_settings(monkeypatch, settings)
    intent = {"action": "deploy", "asset": "model"}
    digest = commitment(intent, domain="intent")["sha256"]
    with pytest.raises(CryptoValidationError, match="legacy_approval_not_allowed"):
        seal(
            payload={"ok": True},
            intent=intent,
            effect=dict(intent),
            approvals=[{
                "approver_id": "manual-operator",
                "intent_digest": digest,
                "proof_type": "manual",
                "proof": "opaque",
            }],
            min_approvals=1,
            workspace_id="v22-lab",
            domain="deployment",
            ttl_seconds=600,
        )


def test_production_api_rejects_zero_approval_threshold(monkeypatch):
    settings = _production_settings()
    _install_settings(monkeypatch, settings)
    monkeypatch.setattr(main_module, "SETTINGS", settings)
    response = client.post(
        "/v1/crypto/seal",
        json={
            "payload": {"ok": True},
            "intent": {"action": "deploy", "asset": "model"},
            "effect": {"action": "deploy", "asset": "model"},
            "approvals": [],
            "min_approvals": 0,
            "domain": "deployment",
            "ttl_seconds": 600,
        },
        headers=HEADERS,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "approval_required_in_production"


def test_production_api_rejects_non_expiring_external_seal(monkeypatch):
    settings = _production_settings()
    _install_settings(monkeypatch, settings)
    monkeypatch.setattr(main_module, "SETTINGS", settings)
    pair = crypto_core.generate_ed25519_approval_keypair()
    intent = {"action": "deploy", "asset": "model"}
    digest = commitment(intent, domain="intent")["sha256"]
    approval = sign_approval(pair["private_key_b64"], digest)
    response = client.post(
        "/v1/crypto/seal",
        json={
            "payload": {"ok": True},
            "intent": intent,
            "effect": intent,
            "approvals": [approval],
            "min_approvals": 1,
            "domain": "deployment",
            "ttl_seconds": 0,
        },
        headers=HEADERS,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "positive_ttl_required_in_production"


def test_production_system_seal_can_use_zero_approval_threshold(monkeypatch):
    settings = _production_settings()
    _install_settings(monkeypatch, settings)
    intent = {"action": "store", "asset": "audit", "recipient": "v22-lab"}
    envelope = seal(
        payload={"system": True},
        intent=intent,
        effect=dict(intent),
        approvals=[],
        min_approvals=0,
        workspace_id="v22-lab",
        domain="at-rest:audit",
        ttl_seconds=0,
    )
    opened = open_envelope(envelope, expected_workspace_id="v22-lab")
    assert opened["content"]["payload"]["system"] is True


def test_same_key_material_is_not_considered_isolated():
    same = _b64(b"k")
    settings = replace(
        SETTINGS,
        environment="production",
        master_keys=(("enc", same),),
        signing_keys=(("sig", same),),
    )
    assert settings.signing_keys_isolated is False
    assert settings.crypto_configured is False


def test_short_signing_key_is_not_ready():
    short = crypto_core._b64e(b"s" * 31)
    settings = replace(
        SETTINGS,
        environment="production",
        master_keys=(("enc", _b64(b"e")),),
        signing_keys=(("sig", short),),
    )
    assert settings.signing_keys_isolated is False
    assert settings.crypto_configured is False


def test_recipient_open_response_schema_preserves_compatibility_fields():
    schema = app.openapi()["components"]["schemas"]["RecipientOpenResponse"]
    required = set(schema.get("required", []))
    assert "ciphertext_sha256" in required
    assert "opened_at" in required


def test_canonical_app_registers_one_recipient_open_route():
    matches = [
        route for route in app.routes
        if getattr(route, "path", None) == "/v1/crypto/open-recipient"
        and "POST" in getattr(route, "methods", set())
    ]
    assert len(matches) == 1


def test_encryption_and_signing_roots_are_isolated(monkeypatch):
    settings = _production_settings()
    _install_settings(monkeypatch, settings)
    intent = {"action": "publish", "asset": "release"}
    digest = commitment(intent, domain="intent")["sha256"]
    approval_pair = crypto_core.generate_ed25519_approval_keypair()
    approval = sign_approval(approval_pair["private_key_b64"], digest)
    envelope = seal(
        payload={"release": "v22"},
        intent=intent,
        effect=dict(intent),
        approvals=[approval],
        min_approvals=1,
        workspace_id="v22-lab",
        domain="release",
        ttl_seconds=600,
    )
    assert envelope["header"]["version"] == "orbythra-effectseal-v2"
    assert envelope["header"]["key_id"] == "enc-v22"
    assert envelope["header"]["signing_key_id"] == "sig-v22"
    opened = open_envelope(envelope, expected_workspace_id="v22-lab", expected_intent_digest=digest)
    assert opened["content"]["payload"]["release"] == "v22"


@pytest.mark.skipif(not pqc_backend_available(), reason="ML-KEM/ML-DSA backend unavailable")
def test_hybrid_pqc_approval_signature_and_recipient_round_trip(monkeypatch):
    settings = _production_settings(pqc_mode="hybrid-required")
    _install_settings(monkeypatch, settings)
    intent = {"action": "transfer", "asset": "evidence", "recipient": "v22-lab"}
    digest = commitment(intent, domain="intent")["sha256"]

    approval_pair = generate_hybrid_approval_keypair()
    approval = sign_hybrid_approval(
        approval_pair["private_key_b64"],
        approval_pair["pq_private_key_b64"],
        digest,
    )
    recipient = generate_hybrid_recipient_keypair()

    envelope = seal(
        payload={"message": "hybrid protected"},
        intent=intent,
        effect=dict(intent),
        approvals=[approval],
        min_approvals=1,
        workspace_id="v22-lab",
        domain="hybrid",
        ttl_seconds=600,
        recipient_public_key_b64=recipient["x25519_public_key_b64"],
        recipient_mlkem768_public_key_b64=recipient["mlkem768_public_key_b64"],
    )

    assert "hybrid_recipient_wrap" in envelope
    assert "recipient_wrap" not in envelope
    assert envelope["pq_signing_algorithm"] == "ML-DSA-65"
    assert envelope["pq_signature_b64"]

    opened = open_hybrid_recipient_envelope(
        envelope,
        expected_workspace_id="v22-lab",
        recipient_x25519_private_key_b64=recipient["x25519_private_key_b64"],
        recipient_mlkem768_private_key_b64=recipient["mlkem768_private_key_b64"],
        expected_signing_public_key_b64=envelope["signing_public_key_b64"],
        expected_pq_signing_public_key_b64=envelope["pq_signing_public_key_b64"],
        expected_intent_digest=digest,
    )
    assert opened["content"]["payload"]["message"] == "hybrid protected"
    assert opened["recipient_verified"] is True


@pytest.mark.skipif(not pqc_backend_available(), reason="ML-KEM/ML-DSA backend unavailable")
def test_hybrid_approval_pq_signature_tamper_fails(monkeypatch):
    settings = _production_settings(pqc_mode="hybrid-required")
    _install_settings(monkeypatch, settings)
    intent = {"action": "approve", "asset": "release"}
    digest = commitment(intent, domain="intent")["sha256"]
    pair = generate_hybrid_approval_keypair()
    approval = sign_hybrid_approval(pair["private_key_b64"], pair["pq_private_key_b64"], digest)
    proof = approval["pq_proof"]
    approval["pq_proof"] = ("A" if proof[0] != "A" else "B") + proof[1:]
    with pytest.raises(CryptoValidationError, match="invalid_hybrid_approval_signature"):
        crypto_core.verify_approvals([approval], intent_digest=digest, min_approvals=1)



def test_effectseal_v2_signature_input_binds_signer_public_keys():
    envelope = {
        "header": {"version": "orbythra-effectseal-v2", "workspace_id": "v22-lab"},
        "ciphertext_b64": "AA",
        "signing_public_key_b64": "classical-a",
        "pq_signing_public_key_b64": "pq-a",
    }
    first = signature_input_for_envelope(envelope)
    envelope["pq_signing_public_key_b64"] = "pq-b"
    second = signature_input_for_envelope(envelope)
    assert first != second


def test_agent_policy_counts_hybrid_signature_as_signed_approval():
    agent = AgentProfile(
        agent_id="v22-agent",
        display_name="V22 Agent",
        allowed_tool_ids=["v22-tool"],
        max_risk_tier="critical",
        human_approval_from_risk="critical",
        signed_approval_from_risk="critical",
    )
    tool = ToolProfile(
        tool_id="v22-tool",
        display_name="V22 Tool",
        protocol="internal",
        allowed_operations=["execute"],
        risk_tier="critical",
    )
    body = AgentActionRequest(
        agent_id="v22-agent",
        tool_id="v22-tool",
        operation="execute",
        risk_tier="critical",
        human_approved=True,
        approvals=[{
            "approver_id": "hybrid:" + "a" * 32,
            "intent_digest": "b" * 64,
            "proof_type": "hybrid_signature",
            "proof": "classical-proof",
            "public_key_b64": "classical-key",
            "pq_public_key_b64": "pq-key",
            "pq_proof": "pq-proof",
        }],
    )
    result = evaluate_agent_policy(agent, tool, body)
    assert result.decision == "ALLOW"
    assert "signed_approval_required" not in result.reasons



def test_agent_approval_backend_failure_blocks_instead_of_500(monkeypatch):
    agent = AgentProfile(
        agent_id="v22-agent-pq",
        display_name="V22 PQ Agent",
        allowed_tool_ids=["v22-tool-pq"],
        max_risk_tier="critical",
        human_approval_from_risk="critical",
        signed_approval_from_risk="critical",
    )
    tool = ToolProfile(
        tool_id="v22-tool-pq",
        display_name="V22 PQ Tool",
        protocol="internal",
        allowed_operations=["execute"],
        risk_tier="moderate",
    )
    body = AgentActionRequest(
        agent_id="v22-agent-pq",
        tool_id="v22-tool-pq",
        operation="execute",
        risk_tier="moderate",
        approvals=[{
            "approver_id": "hybrid:" + "c" * 32,
            "intent_digest": "d" * 64,
            "proof_type": "hybrid_signature",
            "proof": "classical-proof",
            "public_key_b64": "classical-key",
            "pq_public_key_b64": "pq-key",
            "pq_proof": "pq-proof",
        }],
    )

    monkeypatch.setattr(agents_module, "_load_profiles", lambda workspace_id, request_body: (agent, tool))

    def unavailable(*args, **kwargs):
        raise CryptoConfigurationError("pqc_backend_unavailable")

    monkeypatch.setattr(agents_module, "verify_approvals", unavailable)
    decision, reasons, *_ = agents_module._evaluate("v22-lab", body)
    assert decision == "BLOCK"
    assert "pqc_backend_unavailable" in reasons


def test_v2_envelope_issued_with_pqc_off_remains_readable_after_policy_upgrade(monkeypatch):
    issuing = _production_settings(pqc_mode="off")
    _install_settings(monkeypatch, issuing)
    intent = {"action": "store", "asset": "legacy-v22", "recipient": "v22-lab"}
    envelope = seal(
        payload={"value": "preserve-me"},
        intent=intent,
        effect=dict(intent),
        approvals=[],
        min_approvals=0,
        workspace_id="v22-lab",
        domain="at-rest:legacy-v22",
        ttl_seconds=0,
    )
    assert envelope["header"]["pqc_mode"] == "off"
    assert "pq_signature_b64" not in envelope

    upgraded = _production_settings(pqc_mode="hybrid-required")
    _install_settings(monkeypatch, upgraded)
    opened = open_envelope(envelope, expected_workspace_id="v22-lab")
    assert opened["content"]["payload"]["value"] == "preserve-me"


def test_production_api_refuses_replay_protection_disable(monkeypatch):
    monkeypatch.setattr(main_module, "SETTINGS", _production_settings())
    response = client.post(
        "/v1/crypto/open",
        json={"envelope": {}, "enforce_replay_protection": False},
        headers=HEADERS,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "replay_protection_required"
