from datetime import UTC, datetime

from hallucination_guard import (
    CONTRADICTED,
    INSUFFICIENT_EVIDENCE,
    INVALID_PROVENANCE,
    LOW_AUTHORITY,
    MEMORY_ONLY,
    PROVIDER_BLOCKED,
    STALE_EVIDENCE,
    SUPPORTED,
    evaluate_claims,
    verify_claim,
)

NOW = datetime(2026, 9, 29, tzinfo=UTC)
GOOD = {
    "id": "e1",
    "support": 0.95,
    "authority": 0.95,
    "retrieved_at": "2026-09-29T10:00:00Z",
    "url": "https://example.org/source",
    "digest": "sha256:abc",
}

def test_fake_evidence_id_rejected():
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
    old = {**GOOD, "retrieved_at": "2025-01-01T00:00:00Z"}
    assert verify_claim({"evidence_ids": ["e1"], "time_sensitive": True}, [old], now=NOW).status == STALE_EVIDENCE

def test_undated_time_sensitive_evidence_rejected():
    evidence = [{k: v for k, v in GOOD.items() if k != "retrieved_at"}]
    assert verify_claim({"evidence_ids": ["e1"], "time_sensitive": True}, evidence, now=NOW).status == STALE_EVIDENCE

def test_future_dated_evidence_rejected():
    future = {**GOOD, "retrieved_at": "2026-10-30T00:00:00Z"}
    assert verify_claim({"evidence_ids": ["e1"], "time_sensitive": True}, [future], now=NOW).status == STALE_EVIDENCE

def test_memory_is_not_fresh_evidence():
    memory = {**GOOD, "fresh_evidence": False, "memory_kind": "consolidated_fact"}
    assert verify_claim({"evidence_ids": ["e1"]}, [memory], now=NOW).status == MEMORY_ONLY

def test_provider_runtime_block_not_capability_failure():
    blocked = {**GOOD, "provider_blocked": True}
    assert verify_claim({"evidence_ids": ["e1"]}, [blocked], now=NOW).status == PROVIDER_BLOCKED

def test_missing_url_provenance_rejected():
    evidence = [{k: v for k, v in GOOD.items() if k != "url"}]
    assert verify_claim({"evidence_ids": ["e1"]}, evidence, now=NOW).status == INVALID_PROVENANCE

def test_missing_digest_and_locator_rejected():
    evidence = [{k: v for k, v in GOOD.items() if k != "digest"}]
    assert verify_claim({"evidence_ids": ["e1"]}, evidence, now=NOW).status == INVALID_PROVENANCE

def test_locator_can_substitute_for_digest():
    evidence = [{**{k: v for k, v in GOOD.items() if k != "digest"}, "locator": "p. 7"}]
    assert verify_claim({"evidence_ids": ["e1"]}, evidence, now=NOW).status == SUPPORTED

def test_duplicate_evidence_ids_do_not_inflate_support():
    weak = {**GOOD, "support": 0.20}
    claim = {"evidence_ids": ["e1", "e1", "e1"]}
    verdict = verify_claim(claim, [weak], now=NOW)
    assert verdict.status == INSUFFICIENT_EVIDENCE
    assert verdict.bound_evidence_ids == ("e1",)

def test_false_premise_without_evidence_abstains():
    result = evaluate_claims([{"text": "False premise", "evidence_ids": [], "confidence": 0.1}], [], now=NOW)
    assert result["disposition"] == "ABSTAIN_OR_QUALIFY"

def test_unknown_unanswerable_abstains():
    result = evaluate_claims([{"text": "Unknown", "evidence_ids": ["missing"], "confidence": 0.0}], [GOOD], now=NOW)
    assert result["supported_claims"] == 0
    assert result["disposition"] == "ABSTAIN_OR_QUALIFY"

def test_mixed_claims_force_qualification():
    result = evaluate_claims(
        [{"evidence_ids": ["e1"], "confidence": 0.9}, {"evidence_ids": ["missing"], "confidence": 0.2}],
        [GOOD],
        now=NOW,
    )
    assert result["supported_claims"] == 1
    assert result["guarded_claims"] == 1
    assert result["disposition"] == "ABSTAIN_OR_QUALIFY"

def test_all_supported_can_answer():
    evidence = [GOOD, {**GOOD, "id": "e2", "url": "https://example.org/two"}]
    result = evaluate_claims(
        [{"evidence_ids": ["e1"], "confidence": 0.9}, {"evidence_ids": ["e2"], "confidence": 0.8}],
        evidence,
        now=NOW,
    )
    assert result["evidence_gate_pass_rate"] == 1.0
    assert result["disposition"] == "ANSWER"

def test_unsupported_high_confidence_is_overconfidence():
    result = evaluate_claims([{"evidence_ids": ["missing"], "confidence": 0.99}], [GOOD], now=NOW)
    assert result["overconfidence_rate"] == 1.0

def test_unsupported_low_confidence_is_calibrated():
    result = evaluate_claims([{"evidence_ids": ["missing"], "confidence": 0.2}], [GOOD], now=NOW)
    assert result["overconfidence_rate"] == 0.0

def test_empty_claim_set_never_authorizes_answer():
    assert evaluate_claims([], [GOOD], now=NOW)["disposition"] == "ABSTAIN_OR_QUALIFY"
