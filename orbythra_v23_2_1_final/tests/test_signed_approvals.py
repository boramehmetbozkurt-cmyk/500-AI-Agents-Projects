from __future__ import annotations

import copy

import pytest

from app.crypto_core import (
    CryptoValidationError,
    commitment,
    generate_ed25519_approval_keypair,
    seal,
    sign_approval,
    verify_approvals,
)


def test_ed25519_signed_approval_is_verified_and_bound_to_intent():
    intent = {"action": "deploy", "asset": "model", "recipient": "production"}
    digest = commitment(intent, domain="intent")["sha256"]
    pair = generate_ed25519_approval_keypair()
    approval = sign_approval(pair["private_key_b64"], digest)
    accepted = verify_approvals([approval], intent_digest=digest, min_approvals=1)
    assert accepted == [pair["approver_id"]]
    envelope = seal(
        payload={"approved": True},
        intent=intent,
        effect=dict(intent),
        approvals=[approval],
        min_approvals=1,
        workspace_id="signed-approval-lab",
        domain="deployment",
        ttl_seconds=600,
    )
    assert envelope["header"]["approval_count"] == 1


def test_ed25519_signed_approval_rejects_signature_mutation():
    intent = {"action": "deploy", "asset": "model"}
    digest = commitment(intent, domain="intent")["sha256"]
    pair = generate_ed25519_approval_keypair()
    approval = sign_approval(pair["private_key_b64"], digest)
    tampered = copy.deepcopy(approval)
    signature = tampered["proof"]
    tampered["proof"] = ("A" if signature[0] != "A" else "B") + signature[1:]
    with pytest.raises(CryptoValidationError, match="invalid_approval_signature"):
        verify_approvals([tampered], intent_digest=digest, min_approvals=1)


def test_ed25519_signed_approval_rejects_signer_identity_substitution():
    intent = {"action": "deploy", "asset": "model"}
    digest = commitment(intent, domain="intent")["sha256"]
    pair = generate_ed25519_approval_keypair()
    approval = sign_approval(pair["private_key_b64"], digest)
    approval["approver_id"] = "ed25519:" + "0" * 32
    with pytest.raises(CryptoValidationError, match="approval_signer_identity_mismatch"):
        verify_approvals([approval], intent_digest=digest, min_approvals=1)


def test_ed25519_signed_approval_rejects_wrong_intent_digest():
    first = commitment({"action": "deploy", "target": "a"}, domain="intent")["sha256"]
    second = commitment({"action": "deploy", "target": "b"}, domain="intent")["sha256"]
    pair = generate_ed25519_approval_keypair()
    approval = sign_approval(pair["private_key_b64"], first)
    with pytest.raises(CryptoValidationError, match="approval_not_bound_to_intent"):
        verify_approvals([approval], intent_digest=second, min_approvals=1)


def test_signature_proof_requires_public_key():
    digest = commitment({"action": "approve"}, domain="intent")["sha256"]
    with pytest.raises(CryptoValidationError, match="approval_public_key_required"):
        verify_approvals([
            {"approver_id": "ed25519:" + "1" * 32, "intent_digest": digest, "proof_type": "signature", "proof": "opaque"}
        ], intent_digest=digest, min_approvals=1)
