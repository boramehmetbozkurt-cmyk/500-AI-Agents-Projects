from app.verification_firewall_v12 import (
    EvidenceArtifact,
    VerificationFirewallRequest,
    VerificationPolicy,
    verify_candidate_output,
)

RELEASE = "a" * 40
CONFIG = "b" * 64
NONCE = "n" * 24


def request_for(output: str, evidence: list[EvidenceArtifact], **kwargs) -> VerificationFirewallRequest:
    return VerificationFirewallRequest(
        request_id=kwargs.pop("request_id", "v12-test-request"),
        nonce=kwargs.pop("nonce", NONCE),
        model_id=kwargs.pop("model_id", "test-model"),
        prompt=kwargs.pop("prompt", "Answer using evidence."),
        output=output,
        evidence=evidence,
        expected_release_sha=RELEASE,
        configuration_sha256=CONFIG,
        **kwargs,
    )


def test_supported_candidate_passes_and_receipt_binds_output():
    evidence = [EvidenceArtifact(source_id="s1", text="The bridge is open.")]
    first = verify_candidate_output(request_for("The bridge is open.", evidence), now=1000)
    second = verify_candidate_output(request_for("The bridge remains open.", [EvidenceArtifact(source_id="s1", text="The bridge remains open.")]), now=1000)
    assert first.status == "PASS"
    assert first.release_output is True
    assert first.safe_output == "The bridge is open."
    assert first.output_sha256 != second.output_sha256
    assert first.verification_receipt_sha256 != second.verification_receipt_sha256


def test_caller_cannot_hide_unsupported_output_claim():
    body = request_for(
        "The bridge is open. The river is frozen.",
        [EvidenceArtifact(source_id="s1", text="The bridge is open.")],
        required_claims=["The bridge is open."],
    )
    result = verify_candidate_output(body, now=1000)
    assert result.status == "FAIL"
    assert result.release_output is False
    assert result.safe_output == "INSUFFICIENT_EVIDENCE"
    assert "The river is frozen." in result.extracted_claims
    assert any(item.claim == "The river is frozen." and item.status == "UNSUPPORTED" for item in result.claim_verdicts)


def test_evidence_digest_is_recomputed_and_mismatch_fails_closed():
    evidence = [EvidenceArtifact(source_id="s1", text="The bridge is open.", declared_sha256="0" * 64)]
    result = verify_candidate_output(request_for("The bridge is open.", evidence), now=1000)
    assert result.status == "FAIL"
    assert result.invalid_evidence == ["s1:digest_mismatch"]


def test_source_independence_cannot_be_inflated_by_duplicate_lineage():
    evidence = [
        EvidenceArtifact(source_id="mirror-a", independence_key="origin-1", text="The bridge is open."),
        EvidenceArtifact(source_id="mirror-b", independence_key="origin-1", text="The bridge is open."),
    ]
    policy = VerificationPolicy(minimum_independent_sources=2)
    result = verify_candidate_output(request_for("The bridge is open.", evidence, policy=policy), now=1000)
    assert result.status == "FAIL"
    assert result.claim_verdicts[0].independent_support_count == 1
    assert result.claim_verdicts[0].status == "UNSUPPORTED"


def test_future_observation_is_rejected():
    evidence = [EvidenceArtifact(source_id="s1", text="The bridge is open.", observed_at=2000)]
    result = verify_candidate_output(request_for("The bridge is open.", evidence), now=1000)
    assert result.status == "FAIL"
    assert "s1:future_observation" in result.invalid_evidence


def test_semantic_contradiction_blocks_release():
    evidence = [EvidenceArtifact(source_id="s1", text="The bridge is not open.")]
    result = verify_candidate_output(request_for("The bridge is open.", evidence), now=1000)
    assert result.status == "FAIL"
    assert result.claim_verdicts[0].status == "CONTRADICTED"
    assert result.release_output is False


def test_high_risk_output_requires_human_approval():
    evidence = [EvidenceArtifact(source_id="s1", text="The bridge is open.")]
    result = verify_candidate_output(request_for("The bridge is open.", evidence, risk_tier="high"), now=1000)
    assert result.status == "REVIEW"
    assert result.safe_output == "HUMAN_REVIEW_REQUIRED"
    assert result.release_output is False
