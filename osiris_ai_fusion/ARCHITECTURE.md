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
