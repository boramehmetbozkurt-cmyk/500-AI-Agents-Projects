# ORBYTHRA V12 Release Criteria

Status: release gate definition for the V12 assurance candidate.

## 1. Internal full-green gate

A V12 release candidate is internally green only when all of the following are true for the exact candidate SHA:

- GitHub Actions completes with conclusion `success`.
- Application compilation succeeds.
- Full pytest suite succeeds.
- One-million-case adversarial crypto gate succeeds.
- All frozen assurance/generalist/agentic/temporal/distributed/causal benchmark gates succeed.
- Static security scan succeeds at the configured CI severity threshold.
- Dependency vulnerability audit succeeds.
- Repository secret scan succeeds.
- Backup/restore and corruption-recovery drills succeed.
- Kubernetes deployment hardening gate succeeds.
- Production composition and OpenAPI smoke test succeeds.
- V12 focused regression tests for verification, distributed trust, action-chain binding and temporal reality succeed.
- The validation handoff manifest is generated and fingerprinted for the exact release SHA.

A previous successful run does not make a later SHA green. Every material code, policy, benchmark, dependency or deployment change requires a new green run.

## 2. V12 deterministic assurance controls

The tested build must expose and pass regression evidence for:

### Verification firewall
- automatic candidate-output claim extraction;
- claim-to-evidence semantic support and contradiction checks;
- caller inability to omit unsupported output claims;
- evidence digest recomputation;
- future/stale evidence handling;
- source-lineage independence;
- fail-closed release behavior;
- replay protection;
- release/configuration/output/evidence/policy receipt binding.

### Distributed verification
- workspace-isolated validator authority;
- Ed25519 public-key validation;
- revocation and key rotation;
- monotonic registry revisions;
- attestation binding to workspace, payload, nonce and registry revision;
- future/stale attestation rejection;
- duplicate-validator rejection;
- organization-diversity and weighted-quorum controls.

### Action chain
The following order must be cryptographically bound and enforced:

`INTENT -> PLAN -> CANDIDATE -> SIMULATION -> APPROVAL -> ACTION -> EFFECT`

The release must reject stage reordering, replay, stale heads, cross-workspace access and payload tampering. Sensitive action-chain payloads must be encrypted at rest.

### Temporal reality
- valid-time and known/recorded-time separation;
- observation-time and publication-time tracking;
- deterministic historical snapshots;
- validity intervals;
- retirement without rewriting historical known-time views;
- future timestamp checks;
- observation-age staleness;
- source-lineage counting;
- explicit preservation of conflicting facts without silently selecting a winner.

## 3. Independent validation gate

Internal CI does not satisfy this gate.

The release may be described as independently validated only after an external assessor executes `benchmarks/external_validation_protocol_v12.json` against the exact release candidate and provides attributable evidence.

Required external outputs:

1. Independent product-validation report.
2. Independent penetration-test report.
3. Independent cryptographic review or scoped signed findings.
4. Tested Git SHA and deployment/configuration identity.
5. Dataset fingerprint and raw case counts.
6. Results for every primary metric in the V12 external protocol.
7. Security finding table with remediation and retest disposition.
8. Conflict-of-interest and independence disclosure.
9. Protocol-deviation statement.

## 4. Security acceptance

Final acceptance requires:

- zero unresolved Critical findings;
- zero unresolved High findings;
- every Critical/High remediation independently retested;
- Medium/Low findings documented with owner and due date;
- no successful cross-workspace read/write escape in the agreed scope;
- no successful validator spoof/revoked-authority bypass in the agreed scope;
- no successful action-chain tamper/replay bypass in the agreed scope.

## 5. Independence rule

An organization may provide engineering or advisory support, but material contributors to the tested release must not be the sole authority issuing an "independent" validation conclusion. Where the same organization supports both engineering and validation, personnel, evidence handling and decision authority must be separated and disclosed. If that separation is not sufficiently defensible, a second independent assessor is required.

## 6. Change-control after validation

The independent report applies only to the bound release. A material post-validation change to verification policy, cryptography, validator authority, temporal semantics, action governance, authentication/authorization, dependencies, deployment topology or model/provider integration invalidates automatic carry-forward of the validation claim and requires impact assessment plus scoped or full retest.

## 7. Claim boundary

Passing the V12 gates supports a claim that the tested ORBYTHRA release satisfied the defined internal and external engineering-assurance criteria. It does not by itself establish AGI, universal factual correctness, certification of physical engineering designs, zero-risk security, or correctness outside the assessed scope.
