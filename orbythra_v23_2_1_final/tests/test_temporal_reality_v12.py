import uuid

import pytest

from app.temporal_reality_v12 import TEMPORAL_V12, TemporalAssertionIn


def workspace() -> str:
    return "w-" + uuid.uuid4().hex


def assertion(*, value="open", source="s1", lineage=None, valid_from=100, valid_to=None, observed_at=110, published_at=120):
    return TemporalAssertionIn(
        subject="bridge",
        predicate="status",
        object={"value": value},
        valid_from=valid_from,
        valid_to=valid_to,
        observed_at=observed_at,
        published_at=published_at,
        source_id=source,
        source_lineage_id=lineage,
        evidence_sha256=(source[0] if source and source[0] in "abcdef" else "a") * 64,
        confidence=0.9,
    )


def test_bitemporal_snapshot_respects_valid_time_and_known_time():
    wid = workspace()
    first = TEMPORAL_V12.add(wid, assertion(value="open", source="a1"), now=130)
    second = TEMPORAL_V12.add(wid, assertion(value="closed", source="b1", valid_from=200, observed_at=210, published_at=220), now=230)

    at_150_known_150 = TEMPORAL_V12.snapshot(wid, valid_at=150, known_at=150)
    assert [item.fact_id for item in at_150_known_150.facts] == [first.fact_id]

    at_250_known_210 = TEMPORAL_V12.snapshot(wid, valid_at=250, known_at=210)
    assert second.fact_id not in [item.fact_id for item in at_250_known_210.facts]

    at_250_known_250 = TEMPORAL_V12.snapshot(wid, valid_at=250, known_at=250)
    assert second.fact_id in [item.fact_id for item in at_250_known_250.facts]


def test_conflicts_are_preserved_instead_of_silently_selecting_winner():
    wid = workspace()
    TEMPORAL_V12.add(wid, assertion(value="open", source="a1", lineage="origin-a"), now=130)
    TEMPORAL_V12.add(wid, assertion(value="closed", source="b1", lineage="origin-b"), now=131)
    snapshot = TEMPORAL_V12.snapshot(wid, valid_at=150, known_at=150)
    assert len(snapshot.groups) == 1
    assert snapshot.groups[0].status == "CONFLICT"
    assert snapshot.groups[0].source_count == 2
    assert snapshot.groups[0].independent_lineages == 2
    assert len(snapshot.groups[0].object_digests) == 2


def test_mirrored_sources_share_one_independent_lineage():
    wid = workspace()
    TEMPORAL_V12.add(wid, assertion(value="open", source="a1", lineage="origin-a"), now=130)
    TEMPORAL_V12.add(wid, assertion(value="open", source="b1", lineage="origin-a"), now=131)
    snapshot = TEMPORAL_V12.snapshot(wid, valid_at=150, known_at=150)
    assert snapshot.groups[0].status == "CONSISTENT"
    assert snapshot.groups[0].source_count == 2
    assert snapshot.groups[0].independent_lineages == 1


def test_future_observation_and_future_publication_fail_closed():
    wid = workspace()
    with pytest.raises(ValueError, match="future_observation"):
        TEMPORAL_V12.add(wid, assertion(source="a1", observed_at=2000, published_at=2001), now=1000, future_skew_seconds=10)
    with pytest.raises(ValueError, match="future_publication"):
        TEMPORAL_V12.add(wid, assertion(source="b1", observed_at=900, published_at=2000), now=1000, future_skew_seconds=10)


def test_publication_cannot_precede_declared_observation():
    wid = workspace()
    with pytest.raises(ValueError, match="publication_precedes_observation"):
        TEMPORAL_V12.add(wid, assertion(source="a1", observed_at=500, published_at=499), now=1000)


def test_staleness_uses_observation_time_not_recording_time():
    wid = workspace()
    record = TEMPORAL_V12.add(wid, assertion(source="a1", observed_at=100, published_at=110), now=900)
    snapshot = TEMPORAL_V12.snapshot(wid, valid_at=950, known_at=1000, max_observation_age_seconds=500)
    assert record.fact_id in snapshot.stale_fact_ids


def test_duplicate_semantic_assertion_is_rejected():
    wid = workspace()
    item = assertion(source="a1")
    TEMPORAL_V12.add(wid, item, now=130)
    with pytest.raises(ValueError, match="duplicate_temporal_assertion"):
        TEMPORAL_V12.add(wid, item, now=131)


def test_retirement_changes_transaction_time_view_but_not_historical_known_view():
    wid = workspace()
    record = TEMPORAL_V12.add(wid, assertion(source="a1"), now=130)
    TEMPORAL_V12.retire(wid, record.fact_id, "superseded", now=200)
    before_retirement = TEMPORAL_V12.snapshot(wid, valid_at=150, known_at=190)
    after_retirement = TEMPORAL_V12.snapshot(wid, valid_at=150, known_at=210)
    assert record.fact_id in [item.fact_id for item in before_retirement.facts]
    assert record.fact_id not in [item.fact_id for item in after_retirement.facts]


def test_snapshot_is_deterministic_for_same_times_and_data():
    wid = workspace()
    TEMPORAL_V12.add(wid, assertion(source="a1"), now=130)
    one = TEMPORAL_V12.snapshot(wid, valid_at=150, known_at=150)
    two = TEMPORAL_V12.snapshot(wid, valid_at=150, known_at=150)
    assert one.snapshot_sha256 == two.snapshot_sha256
