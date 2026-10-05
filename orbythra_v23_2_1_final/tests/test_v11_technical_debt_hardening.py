import base64,uuid,pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from app.evidence_provenance_v2 import EvidenceSpan,provenance_manifest
from app.causal_intelligence_v11 import CausalRequest,CausalEdge,evaluate
from app.verifiable_intelligence_v6 import EvidenceDocument
from app.distributed_verification_v9 import TRUST_V9,Validator,Attestation,QuorumRequest
from app.persistent_validators_v9 import PERSISTENT_VALIDATORS_V9
def b64(x):return base64.urlsafe_b64encode(x).decode().rstrip("=")
def test_span_binding_changes_on_location():
 t="alpha evidence beta";a=EvidenceSpan(source_id="s",claim="alpha",text=t,start=0,end=5);b=EvidenceSpan(source_id="s",claim="alpha",text=t,start=6,end=14);assert a.digest()!=b.digest() and provenance_manifest([a])["manifest_sha256"]!=provenance_manifest([b])["manifest_sha256"]
def test_temporal_reversal_fails_causal_claim():
 e=CausalEdge(cause="a",effect="b",mechanism="m",evidence_claims=["A causes B"],confidence=.9,confounders=["c"],cause_observed_at=20,effect_observed_at=10);r=evaluate(CausalRequest(request_id="temporal-reversal",hypothesis="h",edges=[e],evidence=[EvidenceDocument(source_id="s",text="A causes B")]),"w");assert r.status=="FAIL" and r.edge_results[0]["temporal_precedence"] is False
def test_collider_confounder_overlap_reviews():
 e=CausalEdge(cause="a",effect="b",mechanism="m",evidence_claims=["A causes B"],confidence=.9,confounders=["x"],colliders=["x"]);r=evaluate(CausalRequest(request_id="collider-review",hypothesis="h",edges=[e],evidence=[EvidenceDocument(source_id="s",text="A causes B")]),"w");assert r.status=="REVIEW"
def test_validator_revocation_and_rotation():
 k=ed25519.Ed25519PrivateKey.generate();i="hard-"+uuid.uuid4().hex;pub=b64(k.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw));PERSISTENT_VALIDATORS_V9.register(Validator(validator_id=i,public_key_b64=pub,organization="o"));PERSISTENT_VALIDATORS_V9.set_active(i,False);assert PERSISTENT_VALIDATORS_V9.get(i).active is False;k2=ed25519.Ed25519PrivateKey.generate();pub2=b64(k2.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw));PERSISTENT_VALIDATORS_V9.rotate(i,pub2);assert PERSISTENT_VALIDATORS_V9.get(i).public_key_b64==pub2
