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

## Benchmarks and what they do not claim

`ops_deep_research_benchmark.py` runs one synthetic corpus through three
configurations of the retrieval pipeline — raw, normalization only, and both
normalization and recursive subquery planning — so each feature's contribution is a
number instead of a claim in prose. It makes no network calls, needs no API keys and
produces byte-identical output on every run, so a reader can reproduce it.

The result file carries its own limits as machine-readable fields, and the Asset
Readiness workflow asserts on them so the data room can never ship it claiming more
than it measures:

- `independent_external_validation: false` — system and harness share an author.
- `third_party_baseline_comparison: false` — comparing against external search, RAG
  or deep-research products requires running those products.
- `models_recall_from_decomposition: false` — the synthetic federation applies no
  relevance ranking and no result truncation, and truncation is the mechanism by
  which decomposition improves recall against a real backend. Modelling it here
  would measure the assumption rather than the system, so `subtopic_coverage` comes
  out identical across variants and is reported that way on purpose.

What the numbers do support: deduplication, which is real because the corpus carries
one document under several URL spellings, and per-question attribution, which is
real because the pipeline issues and records the questions. Both are reported next to
their cost in tool calls.

## Recursive subquery planning

A single-shot planner answers a compound question with one fan-out, so the parts
that need separate research never get it. `subquery.py` decomposes a question into
bounded subquestions and recurses into those, breadth-first.

- **Decomposition is refused more often than attempted.** Each level splits on the
  strongest boundary still present — sentence ends first, then `;` — and leaves the
  rest for the level below, which is what gives recursion somewhere to descend.
  A split is taken only when *every* fragment can stand alone; a half-split that
  strands `"İzmir"` without its predicate is worse evidence than not recursing.
  Coordinating conjunctions (`ve`, `and`) are never boundaries: they join one
  predicate far more often than two questions. When the planner model is enabled it
  handles the cases a regex cannot, and a model outage falls back to the root
  investigation unchanged.
- **Authority is never widened.** Subqueries reuse the tools the root plan already
  sealed, so recursion cannot reach a capability the sealed intent did not
  authorize. `allocate_subquery_calls` enforces this by construction.
- **Budget is never widened.** Subquery calls come out of the tool-call budget the
  root plan left unspent, so enabling recursion redistributes work instead of
  adding it, and `max_tool_calls` remains the ceiling for the whole investigation.
- **Fan-out targets query-sensitive tools only.** OSIRIS feeds return the same
  payload whatever is asked and local kinds reason from the model rather than
  fetching, so asking either a second question would duplicate one payload under
  several questions and manufacture corroboration that does not exist.

Which question a record answers is provenance, so `query` lives inside the evidence
record and inside its digest rather than being annotated on afterwards. Subquery
records share their tool's name; the evidence bundle keys them `tool#sqN`, and
correlation and normalization both group by the record's tool rather than that key
so a tool can never correlate with itself and be reported as two agreeing sources.

Settings: `SUBQUERY_PLANNING_ENABLED` (default true), `SUBQUERY_MAX_COUNT`
(default 3), `SUBQUERY_MAX_DEPTH` (default 2).

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
