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


def test_the_answering_question_is_inside_the_record_and_its_digest():
    # Subquery planning makes one investigation ask several different questions,
    # so which question a record answers is provenance: annotating it after the
    # digest was computed would leave that attribution unsigned.
    root = make_evidence_record(tool="t", source_url="https://e.test", data={"x": 1}, query="root")
    derived = make_evidence_record(tool="t", source_url="https://e.test", data={"x": 1}, query="sub")

    assert root["query"] == "root"
    assert derived["query"] == "sub"
    assert root["digest"] != derived["digest"]
    assert root["evidence_id"] != derived["evidence_id"]


def test_the_bundle_digest_changes_when_a_record_answers_a_different_question():
    a = make_evidence_record(tool="t", source_url="https://e.test", data={"x": 1}, query="root")
    b = make_evidence_record(tool="t", source_url="https://e.test", data={"x": 1}, query="sub")
    assert evidence_bundle_digest({"t": a}) != evidence_bundle_digest({"t": b})
