import uuid

import pytest
from sqlalchemy import text

from app.action_chain_v12 import ACTION_CHAIN_V12, ChainAppendRequest
from app.store import STORE


def workspace() -> str:
    return "w-" + uuid.uuid4().hex


def append_next(workspace_id: str, current, stage: str, payload: dict, *, now: int):
    return ACTION_CHAIN_V12.append(
        workspace_id,
        current.chain_id,
        ChainAppendRequest(stage=stage, payload=payload, expected_previous_entry_sha256=current.head_sha256),
        now=now,
    )


def test_full_action_chain_binds_all_seven_stages():
    wid = workspace()
    current = ACTION_CHAIN_V12.create(wid, {"objective": "deploy safe patch"}, now=1000)
    assert current.next_stage == "PLAN"
    for idx, stage in enumerate(("PLAN", "CANDIDATE", "SIMULATION", "APPROVAL", "ACTION", "EFFECT"), start=1):
        previous_head = current.head_sha256
        current = append_next(wid, current, stage, {"stage": stage, "value": idx}, now=1000 + idx)
        assert current.head_sha256 != previous_head
        assert current.entries[-1].previous_entry_sha256 == previous_head
    assert current.status == "COMPLETE"
    assert current.next_stage is None
    assert current.integrity_verified is True
    assert len(current.entries) == 7


def test_stage_order_is_fail_closed():
    wid = workspace()
    current = ACTION_CHAIN_V12.create(wid, {"objective": "x"}, now=1000)
    with pytest.raises(ValueError, match="action_chain_stage_out_of_order"):
        ACTION_CHAIN_V12.append(
            wid,
            current.chain_id,
            ChainAppendRequest(stage="ACTION", payload={"operation": "write"}, expected_previous_entry_sha256=current.head_sha256),
            now=1001,
        )


def test_stale_head_cannot_append_after_chain_advanced():
    wid = workspace()
    genesis = ACTION_CHAIN_V12.create(wid, {"objective": "x"}, now=1000)
    plan = append_next(wid, genesis, "PLAN", {"plan": 1}, now=1001)
    with pytest.raises(ValueError, match="action_chain_head_mismatch"):
        ACTION_CHAIN_V12.append(
            wid,
            plan.chain_id,
            ChainAppendRequest(stage="CANDIDATE", payload={"candidate": 1}, expected_previous_entry_sha256=genesis.head_sha256),
            now=1002,
        )


def test_chain_is_workspace_isolated():
    wa = workspace()
    wb = workspace()
    current = ACTION_CHAIN_V12.create(wa, {"objective": "x"}, now=1000)
    with pytest.raises(ValueError, match="action_chain_not_found"):
        ACTION_CHAIN_V12.get(wb, current.chain_id)


def test_payload_tampering_is_detected_on_read():
    wid = workspace()
    current = ACTION_CHAIN_V12.create(wid, {"objective": "x"}, now=1000)
    with STORE.engine.begin() as connection:
        connection.execute(
            text("UPDATE action_chain_entries_v12 SET payload_json=:p WHERE workspace_id=:w AND chain_id=:c AND sequence=0"),
            {"p": '{"objective":"tampered"}', "w": wid, "c": current.chain_id},
        )
    reloaded = ACTION_CHAIN_V12.get(wid, current.chain_id)
    assert reloaded.integrity_verified is False


def test_completed_chain_rejects_replay_or_extra_stage():
    wid = workspace()
    current = ACTION_CHAIN_V12.create(wid, {"objective": "x"}, now=1000)
    for idx, stage in enumerate(("PLAN", "CANDIDATE", "SIMULATION", "APPROVAL", "ACTION", "EFFECT"), start=1):
        current = append_next(wid, current, stage, {"n": idx}, now=1000 + idx)
    with pytest.raises(ValueError, match="action_chain_already_complete"):
        ACTION_CHAIN_V12.append(
            wid,
            current.chain_id,
            ChainAppendRequest(stage="EFFECT", payload={"again": True}, expected_previous_entry_sha256=current.head_sha256),
            now=1010,
        )


def test_receipt_changes_when_bound_payload_changes():
    wa = workspace()
    wb = workspace()
    a = ACTION_CHAIN_V12.create(wa, {"objective": "one"}, now=1000)
    b = ACTION_CHAIN_V12.create(wb, {"objective": "two"}, now=1000)
    assert a.chain_receipt_sha256 != b.chain_receipt_sha256
    assert a.entries[0].payload_sha256 != b.entries[0].payload_sha256
