from provenance import confidence_from_evidence, evidence_bundle_digest, make_evidence_record


def test_evidence_digest_is_stable_for_same_records():
    a = make_evidence_record(tool="earthquakes", source_url="https://example.test", data={"x": 1})
    bundle = {"earthquakes": a}
    assert evidence_bundle_digest(bundle) == evidence_bundle_digest(bundle)


def test_confidence_counts_successes():
    evidence = {
        "a": {"ok": True},
        "b": {"ok": False},
    }
    result = confidence_from_evidence(evidence)
    assert result["score"] == 0.5
    assert result["label"] == "medium"
