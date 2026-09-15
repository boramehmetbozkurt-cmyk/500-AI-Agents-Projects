# OSIRIS AI Fusion Architecture

## Product contract

OSIRIS AI Fusion is an evidence-first, authorization-aware research layer over read-only public OSINT
sources. It is not a generic autonomous computer-use agent.

## Request path

1. API authenticates and rate-limits the caller.
2. Planner chooses only registered read-only tools.
3. SEAL v2 creates a canonical intent with scope, expiry, nonce, allow-list and tool budget.
4. Replay guard consumes the nonce before any data call.
5. Collector calls OSIRIS endpoints concurrently with response limits and retries.
6. Provenance layer hashes every evidence record and the evidence bundle.
7. Model router analyzes evidence with a strict untrusted-data boundary.
8. Verifier binds intent, executed tools, evidence digest and analysis digest into a receipt.
9. API returns evidence, confidence metadata, analysis, model identity and receipt.

## Unified evidence schema

Provider federation, the passive feeds and the AI Research Council each answer in
their own shape. `evidence_schema.py` normalizes all of them into one `EvidenceItem`
list so the answer layer, the UI and any external consumer read a single contract
instead of parsing per-provider payloads.

- **Extraction** walks any payload for objects that name a fetchable source. A
  provider result's envelope keys (`source_url`, `provider_id`, `freshness`, …)
  describe the fetch rather than a document and are excluded, so calling more
  providers never manufactures more "sources".
- **Deduplication** keys on a canonical URL: host lowercased and de-`www`-ed,
  scheme normalized, tracking parameters (`utm_*`, `fbclid`, `gclid`, …) dropped,
  query ordered, fragment and trailing slash removed. One document surfaced by
  three providers is one item whose `corroboration` is 3.
- **Ranking** is a fixed, published weighting — provider authority 0.45,
  corroboration 0.30, freshness 0.20, resolvable URL 0.05 — and every item carries
  `score_reasons` explaining its own position. Ordering is deliberately inspectable
  rather than learned, because a research tool has to be able to defend it.
- **Boundary.** Normalization organizes provenance only. It never infers a fact,
  never merges two different documents that happen to agree, and corroboration
  counts independent *origins*, not independent *verification*.

The ranked list is returned as `evidence_items` and a compact projection is placed
ahead of the raw evidence in the analyst prompt, so the citable sources survive
the `max_prompt_evidence_chars` truncation even when the raw payloads do not.

## Why LangGraph is the only required agent framework

LangGraph owns orchestration. Specialist frameworks such as smolagents are optional worker
dependencies and are not imported into the core until a concrete task requires them. AutoGen/CrewAI
should be evaluated as design references or isolated services rather than added to the runtime by
default. This avoids framework overlap and dependency bloat.

## Production scale path

- API: FastAPI replicas behind gateway/WAF.
- Replay protection: replace local SQLite with a transactional shared store when horizontally scaled.
- Queue: add a durable task queue for long investigations/scheduled reports.
- Evidence store: object storage + relational metadata + optional graph database.
- Observability: OpenTelemetry traces/metrics/log aggregation.
- Secrets: KMS/HSM-backed receipt signing and workload identity.
- Model router: local inference first, policy-controlled cloud fallback.
- UI: OSIRIS map consumes evidence coordinates, layers and case state.
