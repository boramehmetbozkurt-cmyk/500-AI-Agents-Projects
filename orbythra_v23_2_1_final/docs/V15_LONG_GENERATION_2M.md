# ORBYTHRA V15 — Governed Long Generation (2M Aggregate Budget)

This extension adds resumable long-form generation without changing the existing per-provider `max_tokens <= 32768` contract.

## Design boundary

`2,000,000` is an aggregate requested output-token budget across multiple provider calls. It is not represented as a single-model-call output limit and it does not override a provider/model's own context or output limits.

At the default `chunk_max_tokens=32768`, a 2,000,000-token aggregate budget requires a minimum of 62 provider calls. The last call receives only the remaining budget.

The provider-neutral layer reports:

- exact aggregate requested token budget;
- exact per-call requested budget;
- provider-neutral UTF-8/4 output-token estimate;
- generated character count;
- per-chunk SHA-256 digest;
- rolling SHA-256 chain receipt.

The estimate is intentionally not described as exact tokenizer usage because each upstream model/provider can tokenize the same text differently.

## ORBYTHRA-native controls used

The implementation is integrated with the existing ORBYTHRA V15 stack rather than bypassing it:

1. Enterprise policy and registered-provider checks are evaluated when a session is created.
2. The same policy is re-evaluated before generation batches.
3. Existing provider gateway allowlists, retries, circuit breaker, URL safety and provider secret handling remain authoritative.
4. Session prompts, continuation tails and generated chunks are encrypted at rest through the existing ORBYTHRA vault.
5. Every chunk is workspace-scoped and auditable.
6. Every chunk receives a SHA-256 content digest and rolling chain receipt.
7. Provider/empty-output failures are recorded into the V15 persistent failure-memory path without masking the original provider error.
8. Existing model-inference usage accounting is preserved.

## API

- `GET /v15/long-generation/readiness`
- `POST /v15/long-generation/sessions`
- `GET /v15/long-generation/sessions/{session_id}`
- `POST /v15/long-generation/sessions/{session_id}/generate`
- `GET /v15/long-generation/sessions/{session_id}/chunks/{chunk_index}`
- `POST /v15/long-generation/sessions/{session_id}/abort`
- `GET /v15/long-generation/sessions/{session_id}/manifest`

`generate` is intentionally resumable and bounded to at most four provider calls per HTTP request. This avoids turning a 62-call job into one fragile, very long HTTP transaction. A caller can repeatedly invoke `generate` until the session reaches `COMPLETE`.

## Compatibility

The existing `ModelInvocationRequest.max_tokens` limit remains unchanged at 32,768. Existing provider gateway behavior and all previous V1–V15 routes remain unchanged. This feature adds a higher-level orchestration layer instead of weakening or replacing the established provider contract.
