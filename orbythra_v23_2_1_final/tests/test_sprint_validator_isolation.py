import base64
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from app.api import app
from app.distributed_verification_v9 import Attestation, TRUST_V9
from app.security import RATE_LIMITER


def test_validator_cannot_be_used_or_overwritten_across_workspaces():
    RATE_LIMITER.reset()
    client = TestClient(app)
    key = Ed25519PrivateKey.generate()
    vid = 'isolation-' + uuid.uuid4().hex
    headers = {'X-API-Key': 'test-secret', 'X-Workspace-ID': 'owner'}
    other = {**headers, 'X-Workspace-ID': 'other'}
    def registration(k):
        return dict(validator_id=vid, public_key_b64=base64.urlsafe_b64encode(k.public_key().public_bytes_raw()).decode(), organization='org')
    assert client.post('/v9/trust/validators', headers=headers, json=registration(key)).status_code == 200
    def body():
        a = Attestation(validator_id=vid, decision='PASS', payload_sha256='a'*64, nonce=uuid.uuid4().hex, issued_at=int(time.time()), signature_b64='pending')
        a.signature_b64 = base64.urlsafe_b64encode(key.sign(TRUST_V9.message(a))).decode()
        return dict(payload_sha256=a.payload_sha256, nonce=a.nonce, attestations=[a.model_dump()], minimum_validators=1)
    assert client.post('/v9/trust/quorum', headers=other, json=body()).json()['status'] == 'FAIL'
    assert client.post('/v9/trust/validators', headers=other, json=registration(Ed25519PrivateKey.generate())).status_code == 200
    assert client.post('/v9/trust/quorum', headers=headers, json=body()).json()['status'] == 'PASS'


def test_registry_failure_never_reports_success(monkeypatch):
    from app.persistent_validators_v9 import PERSISTENT_VALIDATORS_V9
    from app.distributed_verification_v9 import TrustNetwork, Validator
    def unavailable(*args, **kwargs):
        raise RuntimeError('database unavailable')
    monkeypatch.setattr(PERSISTENT_VALIDATORS_V9, 'register', unavailable)
    v = Validator(validator_id='db-failure', public_key_b64=base64.urlsafe_b64encode(Ed25519PrivateKey.generate().public_key().public_bytes_raw()).decode(), organization='org')
    with pytest.raises(RuntimeError, match='database unavailable'):
        TrustNetwork().register(v)


def test_revocation_is_not_bypassed_by_memory_cache():
    from app.persistent_validators_v9 import PERSISTENT_VALIDATORS_V9
    from app.distributed_verification_v9 import Validator
    key = Ed25519PrivateKey.generate()
    vid = 'revoked-' + uuid.uuid4().hex
    TRUST_V9.register(Validator(validator_id=vid, public_key_b64=base64.urlsafe_b64encode(key.public_key().public_bytes_raw()).decode(), organization='org'))
    PERSISTENT_VALIDATORS_V9.set_active(vid, False)
    assert TRUST_V9._lookup(vid).active is False
