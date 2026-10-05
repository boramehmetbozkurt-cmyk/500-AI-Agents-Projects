from app.verifiable_intelligence_v6 import EvidenceDocument,verify_claims
def test_supported_claim_passes():
    r=verify_claims(["Paris is the capital of France"],[EvidenceDocument(source_id="s1",text="Paris is the capital of France.")])
    assert r.status=="PASS" and r.coverage==1
def test_unrelated_claim_fails_closed():
    r=verify_claims(["Paris is the capital of France"],[EvidenceDocument(source_id="s1",text="Berlin is in Germany.")])
    assert r.status=="FAIL" and r.checks[0].verdict=="UNRESOLVED"
def test_negated_evidence_contradicts():
    r=verify_claims(["Paris is the capital of France"],[EvidenceDocument(source_id="s1",text="Paris is not the capital of France.")])
    assert r.status=="FAIL" and r.checks[0].verdict=="CONTRADICTED"
def test_evidence_digest_is_deterministic():
    e=[EvidenceDocument(source_id="s1",text="Paris is the capital of France.")]
    assert verify_claims(["Paris is the capital of France"],e).evidence_sha256==verify_claims(["Paris is the capital of France"],e).evidence_sha256
