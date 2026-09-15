# ORBYTHRA External Validation and Operational Evidence Pack

These templates make real exercises auditable. They do not turn an internal exercise into an independent review.

## Independent Engineering Validation

### Reviewer record

- reviewer name / organization / credentials;
- independence/conflict statement;
- review date and version/Git SHA;
- fixed test cases and rubric frozen before ORBYTHRA answers are disclosed;
- raw ORBYTHRA outputs and baseline outputs;
- scoring sheet and reviewer comments;
- signed/dated conclusion and limitations.

### Minimum rubric

Score each case for numerical correctness, units/dimensions, first-principles reasoning, explicit assumptions, unknowns, alternative comparison, FMEA quality, verification plan, manufacturability/operability constraints and safety/professional-approval boundaries.

A passing internal synthetic benchmark is not independent engineering validation.

## Third-Party Pentest RFP

Provide the assessor with staging/production architecture, OpenAPI schema, authenticated tenant accounts, tenant-isolation requirements, source-review access where agreed, deployment/container configuration and explicit rules of engagement.

Minimum requested coverage:

- authentication, sessions and API keys;
- IDOR and tenant isolation;
- injection and prompt/data boundary abuse;
- SSRF/provider configuration boundary;
- CORS/CSP/security headers;
- rate-limit and quota abuse;
- secret leakage and logs;
- dependencies/container posture;
- Stripe webhook verification when enabled;
- Science Genome privacy boundary;
- evidence/provenance and receipt tampering;
- backup/restore and administrative surfaces.

Retain the original report, severity mapping, remediation commit(s), retest evidence and residual-risk acceptance. The gate closes only after the independent report and remediation evidence exist.

## Secret Rotation Exercise Record

Record without copying secret values:

```text
exercise_id:
environment:
operator(s):
started_at_utc:
completed_at_utc:
credential_classes:
replacement_created: true/false
staging_verified: true/false
production_verified: true/false
old_credentials_revoked: true/false
old_credentials_confirmed_rejected: true/false
new_credentials_confirmed_working: true/false
secret_scan_result:
rollback_needed: true/false
findings:
evidence_locations:
```

## Incident Tabletop Record

```text
exercise_id:
scenario:
participants:
started_at_utc:
ended_at_utc:
severity_declared:
containment_decision:
evidence_preservation_steps:
tenant-isolation checks:
notification/legal questions raised:
root-cause hypothesis:
corrective_actions:
owners_and_due_dates:
retest_results:
evidence_locations:
```

For the default scenario use a suspected cross-tenant data exposure and verify that the team can distinguish UI caching, authentication, query scoping and persistent-storage failures.

## Pilot Evidence Record

A pilot counts only when the counterparty actually uses the product.

```text
counterparty:
approved_use_case:
commercial_status: design-partner / paid-pilot
start_date:
end_date:
baseline_metric:
success_metric:
actual_usage:
outcome:
customer_approval_for_case_study:
contract_or_order_reference:
evidence_locations:
```

Recommended measurable outcomes: research time saved, evidence precision/coverage, engineering review time, incident triage time, analyst throughput or cost per completed investigation. Do not invent ROI percentages.

## Case Study Structure

1. Customer context and authorized use case.
2. Baseline workflow and measurement method.
3. ORBYTHRA configuration/version.
4. Usage window and sample size.
5. Measured outcome with raw-data reference.
6. Limitations and confounders.
7. Customer-approved quote only if written approval exists.
8. Contact/reference status and publication permissions.

## Independent Search/RAG/Deep-Research Benchmark

Freeze cases before outputs are generated. Require the same source-access policy, time limit and cost/accounting rules for ORBYTHRA and each baseline. Preserve prompts, retrieved sources, final answers, latency/tool-call/cost data and evaluator scores.

At minimum score factual correctness, citation support, source quality, duplicate rate, subtopic coverage, unsupported-claim rate, latency and cost. Use `ops_external_benchmark.py` only to aggregate externally supplied results; it does not establish evaluator independence.

## Proprietary Signal Calibration

Pre-register the signal definition, prediction horizon, outcome definition and exclusion rules. Preserve raw signal timestamps before outcomes are known. Supply the observed dataset to `ops_signal_calibration.py` and retain assessor/evidence metadata. Report negative or null calibration results as well as positive ones.
