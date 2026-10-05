import base64
import time
import uuid

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from app.distributed_verification_v12 import (
    AttestationV12,
    QuorumRequestV12,
    TRUST_V12,
    VALIDATORS_V12,
    ValidatorV12,
)


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def keypair():
    private = ed25519.Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return private, b64(public)


def signed_attestation(workspace: str, validator_id: str, private, revision: int, *, payload: str, nonce: str, decision: str = "PASS", issued_at: int = 1000):
    draft = AttestationV12(
        workspace_id=workspace,
        validator_id=validator_id,
        decision=decision,
        payload_sha256=payload,
        nonce=nonce,
        issued_at=issued_at,
        registry_revision=revision,
        signature_b64="placeholder",
    )
    signature = private.sign(TRUST_V12.message(draft))
    return draft.model_copy(update={"signature_b64": b64(signature)})


def test_registry_is_strictly_workspace_isolated():
    validator_id = "iso-" + uuid.uuid4().hex
    workspace_a = "wa-" + uuid.uuid4().hex
    workspace_b = "wb-" + uuid.uuid4().hex
    _, pub_a = keypair()
    _, pub_b = keypair()
    a = VALIDATORS_V12.register(workspace_a, ValidatorV12(validator_id=validator_id, public_key_b64=pub_a, organization="org-a"))
    b = VALIDATORS_V12.register(workspace_b, ValidatorV12(validator_id=validator_id, public_key_b64=pub_b, organization="org-b"))
    assert a.workspace_id == workspace_a and b.workspace_id == workspace_b
    assert a.fingerprint != b.fingerprint
    VALIDATORS_V12.set_active(workspace_a, validator_id, False)
    assert VALIDATORS_V12.get(workspace_a, validator_id).active is False
    assert VALIDATORS_V12.get(workspace_b, validator_id).active is True


def test_attestation_is_bound_to_workspace_and_registry_revision():
    validator_id = "rev-" + uuid.uuid4().hex
    workspace = "w-" + uuid.uuid4().hex
    private, pub = keypair()
    record = VALIDATORS_V12.register(workspace, ValidatorV12(validator_id=validator_id, public_key_b64=pub, organization="org"))
    payload = "a" * 64
    nonce = "nonce-123456"
    old = signed_attestation(workspace, validator_id, private, record.revision, payload=payload, nonce=nonce)
    assert TRUST_V12.verify(workspace, old, payload, nonce, 300, 30, now=1000).validator_id == validator_id

    _, rotated_pub = keypair()
    rotated = VALIDATORS_V12.rotate(workspace, validator_id, rotated_pub)
    assert rotated.revision == record.revision + 1
    with pytest.raises(ValueError, match="validator_revision_mismatch"):
        TRUST_V12.verify(workspace, old, payload, nonce, 300, 30, now=1000)


def test_cross_workspace_attestation_fails_closed():
    validator_id = "cross-" + uuid.uuid4().hex
    workspace_a = "wa-" + uuid.uuid4().hex
    workspace_b = "wb-" + uuid.uuid4().hex
    private, pub = keypair()
    record = VALIDATORS_V12.register(workspace_a, ValidatorV12(validator_id=validator_id, public_key_b64=pub, organization="org"))
    attestation = signed_attestation(workspace_a, validator_id, private, record.revision, payload="b" * 64, nonce="nonce-abcdef")
    with pytest.raises(ValueError, match="attestation_workspace_mismatch"):
        TRUST_V12.verify(workspace_b, attestation, "b" * 64, "nonce-abcdef", 300, 30, now=1000)


def test_malformed_validator_key_is_rejected_without_registration():
    workspace = "w-" + uuid.uuid4().hex
    validator_id = "bad-" + uuid.uuid4().hex
    with pytest.raises(ValueError, match="invalid_ed25519_public_key"):
        VALIDATORS_V12.register(workspace, ValidatorV12(validator_id=validator_id, public_key_b64=b64(b"short"), organization="org"))
    assert VALIDATORS_V12.get(workspace, validator_id) is None


def test_quorum_enforces_independent_organizations():
    workspace = "w-" + uuid.uuid4().hex
    payload = "c" * 64
    nonce = "nonce-quorum-1"
    attestations = []
    for idx, org in enumerate(("org-a", "org-b")):
        private, pub = keypair()
        validator_id = f"q-{idx}-{uuid.uuid4().hex}"
        record = VALIDATORS_V12.register(workspace, ValidatorV12(validator_id=validator_id, public_key_b64=pub, organization=org))
        attestations.append(signed_attestation(workspace, validator_id, private, record.revision, payload=payload, nonce=nonce))
    request = QuorumRequestV12(payload_sha256=payload, nonce=nonce, attestations=attestations, minimum_validators=2, minimum_organizations=2, minimum_pass_fraction=0.67)
    result = TRUST_V12.quorum(workspace, request, now=1000)
    assert result["status"] == "PASS"
    assert result["valid_validators"] == 2
    assert result["valid_organizations"] == 2


def test_future_attestation_is_rejected():
    workspace = "w-" + uuid.uuid4().hex
    private, pub = keypair()
    validator_id = "future-" + uuid.uuid4().hex
    record = VALIDATORS_V12.register(workspace, ValidatorV12(validator_id=validator_id, public_key_b64=pub, organization="org"))
    attestation = signed_attestation(workspace, validator_id, private, record.revision, payload="d" * 64, nonce="nonce-future", issued_at=2000)
    with pytest.raises(ValueError, match="future_attestation"):
        TRUST_V12.verify(workspace, attestation, "d" * 64, "nonce-future", 300, 30, now=1000)
