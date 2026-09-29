from datetime import UTC, datetime

from hallucination_guard import (
    CONTRADICTED,
    INSUFFICIENT_EVIDENCE,
    LOW_AUTHORITY,
    STALE_EVIDENCE,
    SUPPORTED,
    evaluate_claims,
    verify_claim,
)

NOW = datetime(2026, 9, 29, tzinfo=UTC)
GOOD = {"id": "e1", "support": 0.95, "authority": 0.95, "retrieved_at": "2026-09-29T10:00:00Z"}

def test_fake_id_rejected():
    assert verify_claim({"evidence_ids": ["fake"]}, [GOOD], now=NOW).status == INSUFFICIENT_EVIDENCE
def test_strong_real_evidence_supported():
    assert verify_claim({"evidence_ids": ["e1"]}, [GOOD], now=NOW).status == SUPPORTED
def test_contradiction_rejected():
    assert verify_claim({"evidence_ids": ["e1"]}, [{**GOOD, "contradicts": True}], now=NOW).status == CONTRADICTED
def test_weak_support_rejected():
    assert verify_claim({"evidence_ids": ["e1"]}, [{**GOOD, "support": 0.20}], now=NOW).status == INSUFFICIENT_EVIDENCE
def test_low_authority_rejected():
    assert verify_claim({"evidence_ids": ["e1"]}, [{**GOOD, "authority": 0.20}], now=NOW).status == LOW_AUTHORITY
def test_stale_time_sensitive_evidence_rejected():
    assert verify_claim({"evidence_ids": ["e1"], "time_sensitive": True}, [{**GOOD, "retrieved_at": "2025-01-01T00:00:00Z"}], now=NOW).status == STALE_EVIDENCE
def test_undated_time_sensitive_evidence_rejected():
    evidence = [{k: v for k, v in GOOD.items() if k != "retrieved_at"}]
    assert verify_claim({"evidence_ids": ["e1"], "time_sensitive": True}, evidence, now=NOW).status == STALE_EVIDENCE
def test_mixed_claims_force_qualification():
    result = evaluate_claims([{"evidence_ids": ["e1"]}, {"evidence_ids": ["missing"]}], [GOOD], now=NOW)
    assert result["supported_claims"] == 1 and result["guarded_claims"] == 1 and result["disposition"] == "ABSTAIN_OR_QUALIFY"
def test_all_supported_can_answer():
    result = evaluate_claims([{"evidence_ids": ["e1"]}, {"evidence_ids": ["e2"]}], [GOOD, {**GOOD, "id": "e2", "support": 0.90, "authority": 0.80}], now=NOW)
    assert result["evidence_gate_pass_rate"] == 1.0 and result["disposition"] == "ANSWER"
def test_empty_claim_set_never_authorizes_answer():
    assert evaluate_claims([], [GOOD], now=NOW)["disposition"] == "ABSTAIN_OR_QUALIFY"
