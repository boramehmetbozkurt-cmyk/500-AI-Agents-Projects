# ORBYTHRA V21 — Assurance & Observability

V21 closes the main AI-engineering observability and evaluation gaps identified against Arize Phoenix, LangSmith, Langfuse, Galileo and Patronus while preserving ORBYTHRA's evidence, policy, cryptographic authorization and outcome-verification model.

## Added in V21

### Versioned evaluation datasets
- workspace-scoped dataset registry;
- immutable dataset versions;
- SHA-256 content binding;
- source-reference metadata;
- encrypted examples at rest;
- deterministic example counts and version numbers.

### Immutable prompt versions
- named prompt registry;
- append-only prompt versions;
- model, parameter and tag binding;
- SHA-256 prompt manifests;
- encrypted prompt payloads at rest.

### Reproducible experiments
- frozen dataset-version + prompt-version + model binding;
- result records by example/repetition;
- arbitrary numeric evaluator scores;
- latency, token and cost accounting;
- sealed experiments;
- baseline/candidate metric comparison with minimum-improvement gates.

### W3C / OTLP observability
- W3C `traceparent` ingestion and propagation;
- server request trace/span generation;
- optional dependency-free OTLP/HTTP JSON export;
- OpenInference-compatible span-kind attributes;
- bounded in-memory exporter queue;
- exporter failure isolation from the request path.

### Trace-to-assurance lineage
V21 can bind a trace span to three independently supplied hashes:

```text
Trace Span
  -> Evidence Manifest SHA-256
  -> Policy Decision SHA-256
  -> Outcome Receipt SHA-256
  -> Lineage SHA-256
```

This allows an operational trace to be connected to ORBYTHRA's assurance chain rather than remaining only an observability record.

## Security model

Dataset examples, prompts, experiment metadata/results and trace attributes use the existing ORBYTHRA vault for encrypted persistence when cryptographic configuration is present. Workspace isolation and RBAC are inherited from the existing security layer.

V21 does not allow an experiment record, trace or evaluator score to grant new agent/tool authority. It does not bypass policy evaluation, approvals, EffectSeal authorization, execution-time revalidation or outcome verification.

## OTLP configuration

```env
ORBYTHRA_OTLP_ENDPOINT=https://collector.example.com
ORBYTHRA_OTLP_SERVICE_NAME=orbythra
ORBYTHRA_OTLP_HEADERS=Authorization=Bearer replace-me
```

If the endpoint does not end in `/v1/traces`, ORBYTHRA appends that standard OTLP trace path. Export is opt-in; when disabled, W3C trace context and local recent-span telemetry remain available.

## Claim boundary

V21 provides internal engineering controls and reproducible evidence. It does not by itself establish independent product validation, independent penetration-test approval, independent cryptographic review, regulatory certification, production reliability history, universal factual correctness or AGI.
