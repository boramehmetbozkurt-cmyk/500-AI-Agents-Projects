from hallucination_guard import (
    CONTRADICTED,
    INSUFFICIENT_EVIDENCE,
    SUPPORTED,
    evaluate_claims,
    verify_claim,
)

def test_fake_evidence_id_cannot_pass():
    verdict = verify_claim({"evidence_ids": ["fake"]}, [{"id": "real", "support": 1.0}])
    assert verdict.status == INSUFFICIENT_EVIDENCE
    assert verdict.bound_evidence_ids == ()

def test_real_supported_claim_passes():
    verdict = verify_claim({"evidence_ids": ["e1"]}, [{"id": "e1", "support": 0.95}])
    assert verdict.status == SUPPORTED

def test_contradiction_forces_guard():
    verdict = verify_claim({"evidence_ids": ["e1"]}, [{"id": "e1", "support": 1.0, "contradicts": True}])
    assert verdict.status == CONTRADICTED

def test_weak_support_forces_guard():
    verdict = verify_claim({"evidence_ids": ["e1"]}, [{"id": "e1", "support": 0.2}])
    assert verdict.status == INSUFFICIENT_EVIDENCE

def test_mixed_claims_abstain_or_qualify():
    result = evaluate_claims(
        [{"evidence_ids": ["e1"]}, {"evidence_ids": ["missing"]}],
        [{"id": "e1", "support": 0.9}],
    )
    assert result["supported_claims"] == 1
    assert result["guarded_claims"] == 1
    assert result["unsupported_claim_rate"] == 0.5
    assert result["disposition"] == "ABSTAIN_OR_QUALIFY"

def test_all_supported_can_answer():
    result = evaluate_claims(
        [{"evidence_ids": ["e1"]}, {"evidence_ids": ["e2"]}],
        [{"id": "e1", "support": 0.9}, {"id": "e2", "support": 0.8}],
    )
    assert result["unsupported_claim_rate"] == 0.0
    assert result["disposition"] == "ANSWER"
