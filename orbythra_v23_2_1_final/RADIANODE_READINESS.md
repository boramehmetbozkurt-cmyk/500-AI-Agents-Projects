# Radianode controlled evaluation readiness

Status: CONDITIONALLY READY for scoped assessor evaluation; no production or independent-validation claim.

## A. Demonstrated working

Baseline main `2dea627f20bff44032b0843af920cad6c46c4b24`: GitHub Actions run
36910780452 passed 745 tests, frontend build, Compose syntax, internal security
scans and the existing deterministic gates. These are baseline results only.
The sprint adds regression tests for cross-workspace validator use/overwrite,
failed persistence, revocation, malformed source URLs, source sentence splitting,
all protected operations with missing/invalid auth, and explicit registry outage.
Use the PR's exact CI SHA and attached JUnit results for the candidate verdict.

## B. Implemented — internal validation only

- Workspace-scoped V9 registry; persistence is authoritative, including revocation.
- Demo credential injection at the nginx server, never in the React bundle.
- Python dependency constraints and npm lock; CI uploads JUnit, SBOM and JSON gate artifacts.
- SHA-256 handoff manifests; source/test files and dependency locks are fingerprinted.
- Assessor JSONL harness supports at least 1,000 cases across ten categories.
  Its mocked 1,000-request unit test tests the harness only, not product accuracy.

## C. Experimental

Lexical/NLI evidence signals, generalist/causal/cognitive decision modules and
engineering envelopes require representative independent evaluation. Their API
version numbers do not establish scientific validity or AGI.

## D. Known limitations

- No workflow named V15 Final Gate exists in this repository; do not report it green.
- Version metadata retains compatibility values (4.0.0 / current release 5.1.0)
  while routes include v11h. Identify the candidate by exact SHA.
- Legacy global validators are retained for internal compatibility and are NOT
  trusted by workspace API calls. Re-register each validator in its intended workspace.
- Static API keys are deployment credentials and may select workspaces. Use
  validated OIDC workspace claims for tenant-bound identities; do not distribute
  a deployment key to untrusted tenants. Workspace scoping alone is not tenant authorization.
- Demo is loopback-only by default and uses public demo credentials. It is not a
  safe shared/public deployment; production requires distinct secrets and identity controls.
- Live SerpAPI/provider evaluation requires server-side credentials and a quota.
- Temporal storage distinguishes valid and recorded time; separate observation/
  publication times and a complete correction lifecycle are not demonstrated.
- Base container tags are mutable; fully hermetic image/dependency provenance is not claimed.
- Complete Docker/PostgreSQL/Ollama runtime, restart/persistence and provider outage
  validation require a Docker-capable environment. Build/syntax checks are insufficient. The candidate CI adds a production
  nginx/API/PostgreSQL startup/readiness/auth smoke; its result is recorded in CI.
- Not every endpoint has every dependency-failure permutation tested. Model output
  gate PASS describes supplied evidence checks, not independent factual verification.

## E. External validation required

Assessor-owned cases, acceptance thresholds and grading; engineering quantitative
traceability and uncertainty review; independent security/crypto assessment;
controlled deployment evidence and signed conclusions bound to the tested SHA.

## Execute the external harness

Install `requirements-dev.txt` with `-c requirements.lock`. Use an isolated
deployment: cases may mutate data. Set `ORBYTHRA_EVALUATOR_API_KEY` server-side.
Then run:

```sh
python scripts/external_validation_harness.py assessor-cases.jsonl \
  --base-url http://127.0.0.1:8000 --release-sha EXACT_DEPLOYED_SHA \
  --output assessor-results.json
```

Each JSONL object requires unique `case_id`, `category`, relative `path`,
`expected_status`, and (for success) `expected_json` with exact top-level values.
Optional fields: `method`, `body`, `workspace`, `auth` (`valid`, `missing`, `invalid`).
Categories: claim_evidence, engineering_reasoning, first_principles,
quantitative_traceability, temporal_reality, distributed_verification,
governed_actions, security, tenant_isolation, failure_behaviour.
Supply >=1,000 cases covering every category. Dataset and report SHA-256 hashes
are recorded; nonzero exit means failures. The assessor must retain private raw
evidence and document sampling, blinding, statistical analysis and deviations.
The earlier 500-case v1 protocol remains historical; this sprint's harness uses
the >=1,000-case scope and does not claim that those external cases were run.
