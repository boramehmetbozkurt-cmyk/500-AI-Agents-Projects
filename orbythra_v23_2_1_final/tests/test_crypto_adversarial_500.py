from __future__ import annotations

import copy

import pytest

from app.crypto_core import CryptoValidationError, commitment, open_envelope, seal

WORKSPACE = "adversarial-512"


def _seal(algorithm: str, marker: int) -> dict:
    intent = {"action":"transfer","asset":"USDC","amount":str(marker+1),"recipient":"alice","chain":"base","fee":"0.01"}
    digest = commitment(intent, domain="intent")["sha256"]
    envelope = seal(
        payload={"message":f"protected-{marker}"},
        intent=intent,
        effect=dict(intent),
        approvals=[{"approver_id":"adversarial-tester","intent_digest":digest,"proof_type":"gesture","proof":"opaque-proof"}],
        min_approvals=1,
        workspace_id=WORKSPACE,
        domain="adversarial-validation",
        ttl_seconds=600,
        algorithm=algorithm,
    )
    return {"envelope":envelope,"intent_digest":digest}


def _mutate(value: str, index: int) -> str:
    pos=index % max(1,len(value)-1)
    repl="A" if value[pos]!="A" else "B"
    return value[:pos]+repl+value[pos+1:]


@pytest.mark.parametrize("case", range(128))
def test_aes256_gcm_ciphertext_tamper_fails_closed(case: int):
    sealed=_seal("aes256-gcm",case)
    tampered=copy.deepcopy(sealed["envelope"])
    tampered["ciphertext_b64"]=_mutate(tampered["ciphertext_b64"],case)
    with pytest.raises(CryptoValidationError):
        open_envelope(tampered,expected_workspace_id=WORKSPACE)


@pytest.mark.parametrize("case", range(128))
def test_chacha20_poly1305_ciphertext_tamper_fails_closed(case: int):
    sealed=_seal("chacha20-poly1305",1000+case)
    tampered=copy.deepcopy(sealed["envelope"])
    tampered["ciphertext_b64"]=_mutate(tampered["ciphertext_b64"],case)
    with pytest.raises(CryptoValidationError):
        open_envelope(tampered,expected_workspace_id=WORKSPACE)


@pytest.mark.parametrize("case", range(128))
def test_wrong_intent_commitment_is_rejected(case: int):
    sealed=_seal("aes256-gcm",2000+case)
    wrong=commitment({"action":"transfer","amount":"999999","recipient":f"mallory-{case}"},domain="intent")["sha256"]
    with pytest.raises(CryptoValidationError,match="intent_commitment_mismatch"):
        open_envelope(sealed["envelope"],expected_workspace_id=WORKSPACE,expected_intent_digest=wrong)


@pytest.mark.parametrize("case", range(128))
def test_signature_tamper_is_rejected(case: int):
    sealed=_seal("aes256-gcm",3000+case)
    tampered=copy.deepcopy(sealed["envelope"])
    tampered["signature_b64"]=_mutate(tampered["signature_b64"],case)
    with pytest.raises(CryptoValidationError):
        open_envelope(tampered,expected_workspace_id=WORKSPACE)
