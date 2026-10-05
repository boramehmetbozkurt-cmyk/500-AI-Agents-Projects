from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.api import app
from app.long_generation_v15 import LONG_GENERATION_V15, LongGenerationSessionRequest, _estimate_tokens


def wid(prefix: str = "lg") -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def request(*, target: int = 2_000_000, chunk: int = 32_768) -> LongGenerationSessionRequest:
    return LongGenerationSessionRequest(
        provider_id="provider-a",
        model_id="model-a",
        messages=[{"role": "user", "content": "Produce a long verified technical report."}],
        target_total_tokens=target,
        chunk_max_tokens=chunk,
        continuation_overlap_chars=1000,
    )


def test_two_million_budget_is_accepted_without_changing_per_call_cap() -> None:
    body = request()
    assert body.target_total_tokens == 2_000_000
    assert body.chunk_max_tokens == 32_768
    with pytest.raises(ValidationError):
        request(target=2_000_001)
    with pytest.raises(ValidationError):
        request(chunk=32_769)


def test_two_million_budget_plans_sixty_two_provider_calls() -> None:
    workspace = wid("plan")
    session = LONG_GENERATION_V15.create(workspace, "tester", request(), now=1000)
    assert session.minimum_planned_chunks == 62
    assert session.allocated_output_token_budget == 0
    assert session.progress == 0.0


def test_chunking_reaches_exact_aggregate_budget_and_preserves_hash_chain() -> None:
    workspace = wid("complete")
    session = LONG_GENERATION_V15.create(workspace, "tester", request(), now=1000)
    previous_chain = None
    remaining = session.target_total_tokens
    index = 0
    while remaining > 0:
        budget = min(session.chunk_max_tokens, remaining)
        text_value = f"chunk-{index}-" + ("x" * 32)
        text_sha = __import__("hashlib").sha256(text_value.encode("utf-8")).hexdigest()
        chain_sha = __import__("hashlib").sha256(f"{previous_chain}|{index}|{text_sha}|{budget}".encode("utf-8")).hexdigest()
        stored = LONG_GENERATION_V15.append_chunk(
            workspace,
            session.session_id,
            chunk_index=index,
            text_value=text_value,
            requested_token_budget=budget,
            estimated_output_tokens=_estimate_tokens(text_value),
            text_sha256=text_sha,
            chain_sha256=chain_sha,
            request_reference=f"ref-{index}",
            latency_ms=1.0,
            last_tail=text_value[-16:],
            now=1001 + index,
        )
        assert stored.chunk_index == index
        previous_chain = chain_sha
        remaining -= budget
        index += 1

    final = LONG_GENERATION_V15.get(workspace, session.session_id)
    assert final is not None
    assert final.status == "COMPLETE"
    assert final.allocated_output_token_budget == 2_000_000
    assert final.next_chunk_index == 62
    assert final.progress == 1.0
    assert final.last_chain_sha256 == previous_chain
    assert len(LONG_GENERATION_V15.chunk_hashes(workspace, session.session_id)) == 62


def test_long_generation_storage_is_workspace_isolated_and_encrypted() -> None:
    workspace = wid("isolation")
    other = wid("other")
    session = LONG_GENERATION_V15.create(workspace, "tester", request(target=1024, chunk=512), now=1000)
    assert LONG_GENERATION_V15.get(other, session.session_id) is None
    protected = LONG_GENERATION_V15.protected_request(workspace, session.session_id)
    assert protected is not None
    assert protected["messages"][0]["content"] == "Produce a long verified technical report."

    row = LONG_GENERATION_V15._row(workspace, session.session_id)
    assert row is not None
    raw = str(row["encrypted_request_json"])
    assert "Produce a long verified technical report." not in raw


def test_production_composition_exposes_long_generation_routes() -> None:
    paths = set(app.openapi()["paths"])
    assert "/v15/long-generation/readiness" in paths
    assert "/v15/long-generation/sessions" in paths
    assert "/v15/long-generation/sessions/{session_id}/generate" in paths
    assert "/v15/long-generation/sessions/{session_id}/manifest" in paths


def test_long_generation_session_survives_store_reinstantiation() -> None:
    from app.long_generation_v15 import LongGenerationStoreV15

    workspace = wid("restart")
    writer = LongGenerationStoreV15()
    created = writer.create(workspace, "tester", request(target=2048, chunk=512), now=1000)

    reader_after_restart = LongGenerationStoreV15()
    restored = reader_after_restart.get(workspace, created.session_id)
    protected = reader_after_restart.protected_request(workspace, created.session_id)

    assert restored is not None
    assert restored.session_id == created.session_id
    assert restored.status == "ACTIVE"
    assert restored.target_total_tokens == 2048
    assert protected is not None
    assert protected["messages"][0]["content"] == "Produce a long verified technical report."
