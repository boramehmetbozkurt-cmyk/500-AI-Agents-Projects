import base64,time
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from app.distributed_verification_v9 import TRUST_V9,Validator,Attestation,QuorumRequest
def b64(x):return base64.urlsafe_b64encode(x).decode().rstrip("=")
def make(i,decision="PASS",h="a"*64,nonce="nonce-12345"):
 k=ed25519.Ed25519PrivateKey.generate();pub=b64(k.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw));v=Validator(validator_id=i,public_key_b64=pub,organization=i);TRUST_V9.register(v);a=Attestation(validator_id=i,decision=decision,payload_sha256=h,nonce=nonce,issued_at=int(time.time()),signature_b64="x");a.signature_b64=b64(k.sign(TRUST_V9.message(a)));return a
def test_three_validator_quorum_passes():assert TRUST_V9.quorum(QuorumRequest(payload_sha256="a"*64,nonce="nonce-12345",attestations=[make("v91"),make("v92"),make("v93")]))["status"]=="PASS"
def test_byzantine_fail_vote_prevents_threshold():assert TRUST_V9.quorum(QuorumRequest(payload_sha256="a"*64,nonce="nonce-12345",attestations=[make("v94"),make("v95","FAIL"),make("v96","FAIL")]))["status"]=="FAIL"
def test_duplicate_validator_not_double_counted():
 a=make("v97");r=TRUST_V9.quorum(QuorumRequest(payload_sha256="a"*64,nonce="nonce-12345",attestations=[a,a],minimum_validators=2));assert r["status"]=="FAIL" and r["invalid"][0]["reason"]=="duplicate_validator"
def test_wrong_payload_signature_fails_closed():
 a=make("v98");r=TRUST_V9.quorum(QuorumRequest(payload_sha256="b"*64,nonce="nonce-12345",attestations=[a],minimum_validators=1));assert r["status"]=="FAIL"
