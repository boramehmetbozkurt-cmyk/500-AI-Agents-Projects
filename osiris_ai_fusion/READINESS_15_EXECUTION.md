# ORBYTHRA — 15-Gate External Readiness Execution Pack

This register separates **software preparation** from **real external evidence**. No gate is marked complete merely because a template, script or workflow exists. A gate closes only when its required evidence exists and can be reviewed.

## Status legend

- **READY TO EXECUTE** — repository/tooling side is complete; an owner/external action can now generate the evidence.
- **PARTIAL** — internal evidence exists, but an independent/production/customer result is still required.
- **EXTERNAL GATE** — cannot be truthfully completed by repository changes alone.

## 1. Hosted public buyer demo — READY TO EXECUTE

The buyer-safe public interface exists in `orbythra_live_demo/`. The one-click deployment branch/PR provides a zero-secret Render static deployment. The full backend remains separately deployable. Close this gate only after a public HTTPS URL is recorded and tested from outside the deployment account.

Evidence to retain: URL, deployment provider/service ID, first-live UTC timestamp, screenshot or HTTP evidence, release Git SHA.

## 2. Production domain + uptime history — READY TO EXECUTE / EXTERNAL GATE

`ops_production_probe.py` and the `ORBYTHRA Production Evidence` workflow collect bounded external `/health` probes, success rate and p50/p95/p99 latency. Configure repository variable `ORBYTHRA_PRODUCTION_BASE_URL`; optional authenticated probes can use `ORBYTHRA_PRODUCTION_API_KEY`.

A single successful run does **not** equal uptime history. Initial diligence should retain at least seven days; mature evidence should retain 30+ days.

## 3. Real signed release attestation — READY TO EXECUTE / EXTERNAL GATE

`ops_attestation.py` already performs Ed25519 signing. The dedicated manual signed-release workflow now fails closed unless the owner supplies `ORBYTHRA_ATTESTATION_ED25519_PRIVATE_KEY_B64`. Close only when an uploaded release artifact has `signature.signed=true`, the release Git SHA and reviewable SHA-256 subjects.

Never commit the private key.

## 4. Production load/SLO history — READY TO EXECUTE / EXTERNAL GATE

Production probe artifacts now create the beginning of an external time series. `/metrics` and `/slo` expose application-side data for administrators. A real SLO claim requires retained production observations, request counts, 5xx data, latency, incidents and error-budget history.

## 5. Independent engineering validation — EXTERNAL GATE

Give an independent qualified engineering reviewer a fixed case set before they see ORBYTHRA output. Require numerical correctness, assumptions/unknowns, unit consistency, alternatives, FMEA, verification plan and safety-boundary scoring. Retain reviewer identity/organization, case definitions, rubric, raw outputs, scores and signed/dated result. Internal synthetic cases remain regression tests, not independent validation.

## 6. Third-party pentest — EXTERNAL GATE

The threat model and pentest scope are ready. Commission a third party with authenticated tenant accounts and source access as contractually appropriate. Minimum scope: authentication, IDOR/tenant isolation, injection, SSRF/provider boundary, CORS/CSP, rate limits, secret leakage, dependency/container posture, billing webhooks, science/genome privacy and provenance tampering. Close only after report plus remediation/retest evidence exists.

## 7. Real secret rotation + incident tabletop — READY TO EXECUTE / EXTERNAL GATE

`enterprise/OPS_EVIDENCE_RUNBOOK.md` defines both exercises. Evidence must be dated and tied to a real environment. Record credential class only, never the secret. For tabletop evidence include participants, scenario, timeline, findings, decisions, corrective actions and retest status.

## 8. Standalone ORBYTHRA repo — READY TO EXECUTE

`scripts/build_standalone_repo.py` creates a git-ready ORBYTHRA source export, excludes local secrets/databases and preserves the upstream MIT notice. This closes the **local carve-out** task. A remote standalone repository remains external until one is actually created and its access/ownership is recorded.

## 9. Trademark/domain ownership package — EXTERNAL GATE

Prepare evidence for ORBYTHRA marks and domains: registrant/legal owner, registrar, domain, acquisition/registration date, renewal date, account evidence, DNS control test, trademark jurisdiction/class/application number/status and counsel/search memo where available. Preliminary name searches are not a filing and do not prove clearance.

Do not use the ® symbol before registration.

## 10. Contributor assignment / counsel IP review — EXTERNAL GATE

Retain a contributor register, employment/contract basis for each material contributor, signed assignment where required, third-party/open-source schedule, data-license schedule and final counsel-reviewed IP schedule. The upstream MIT material must remain identified and licensed; it must not be represented as exclusive ORBYTHRA IP.

## 11. Large real dataset ingest measurement — READY TO EXECUTE / EXTERNAL DATA REQUIRED

`ops_dataset_ingest_benchmark.py` runs the actual resumable `science_importer` against a supplied OpenAlex/Ensembl/NCBI/UniProt JSONL or JSONL.GZ file and records source hash/size, throughput, entity counts, errors and DB growth. The tool deliberately sets `production_scale_claim=false`; buyer evidence becomes production-scale only when the real snapshot/release/environment is documented.

## 12. Proprietary signal external calibration — READY TO EXECUTE / EXTERNAL GATE

`ops_signal_calibration.py` accepts observed outcomes and calculates Brier score, expected calibration error, bins and signal/outcome correlation. `external_claim_ready` remains false unless a named independent assessor and reviewable evidence URI are supplied. Calibration on internally invented outcomes does not close this gate.

## 13. 2–5 real pilots — EXTERNAL GATE

Use the enterprise pilot playbook. A pilot counts only when there is a named counterparty, approved use case, start/end dates, success metric, actual usage and a documented outcome. Design-partner conversations without product use are interviews, not pilots.

## 14. Real ARR/MRR, usage, retention and case study — READY TO MEASURE / EXTERNAL GATE

`ops_commercial_metrics.py` computes MRR/ARR run rate, 30-day activity/retention and usage from supplied account exports. Buyer claims require source-system identity and reviewable evidence. A case study should include baseline, ORBYTHRA workflow, measured time/cost/quality delta, customer approval and limitations.

## 15. Independent external search/RAG/deep-research benchmark — READY TO SCORE / EXTERNAL GATE

`ops_external_benchmark.py` aggregates externally supplied case-level scores across ORBYTHRA and at least one third-party baseline. It calculates mean/median/range and win share. `external_claim_ready` becomes true only when the evaluator explicitly identifies independent external validation, third-party comparison, a named assessor and reviewable evidence URI.

The internal ablation benchmark remains useful regression evidence but does not substitute for this gate.

## Definition of done

A gate closes only when its artifact is retained in the buyer data room and the evidence itself supports the claim. Scripts, workflows, templates and protocols make the work reproducible; they never fabricate elapsed uptime, external independence, ownership, legal approval, customer usage or revenue.
