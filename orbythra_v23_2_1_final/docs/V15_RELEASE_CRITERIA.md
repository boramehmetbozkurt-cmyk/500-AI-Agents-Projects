# ORBYTHRA V15.0 Release Criteria

Status: internal final-hardening candidate. These criteria separate repository-controlled readiness from externally attributable validation.

## A. Internal V15 full-green gate

A candidate may be called **V15 internal full green** only when all of the following are true for one exact commit SHA:

1. The complete repository CI workflow succeeds with no skipped required gate caused by configuration failure.
2. The V12 assurance baseline remains green, including adversarial crypto, frozen assurance/generalist/agentic/temporal/distributed/causal benchmarks, recovery, deployment, static security, dependency audit, SBOM and secret scan.
3. `tests/test_v15_final_hardening.py` passes in the normal test suite.
4. Production OpenAPI composition exposes the V15 readiness surfaces.
5. The V15 failure-memory release gate has no unresolved High or Critical OPEN/REGRESSION record for the release workspace used for qualification.
6. No release claim states that internal CI is an independent audit, certification, real-world sensing proof, universal factuality proof, or commercial production history.

## B. V15 control objectives

### Calibrated trust

- Brier score and expected calibration error are computed from labeled outcomes.
- Calibration is scoped by workspace/domain/task.
- Under-sampled domains do not receive synthetic confidence improvement.
- Calibration output remains an empirical estimate, not a truth guarantee.

### Agent control plane

- Kill/suspend decisions are enforced at execution time, not only at proposal time.
- Workspace emergency stop blocks execution.
- Capability allowlists and risk ceilings are fail-closed once a V15 control record exists.
- Control-policy changes advance an epoch and are auditable.

### Effect verification

- Observed effect is compared against the committed intended-effect digest.
- Independent lineage counting prevents duplicated mirrors from inflating consensus.
- Future/stale observations are rejected or made inconclusive.
- High/Critical risk may require a V12 validator quorum bound to the observation manifest.
- The system must not claim it sensed the external world when observations were supplied by another adapter/system.

### Multimodal evidence

- Content and metadata hashes, provenance, lineage and time are bound in a deterministic manifest.
- Duplicate content, missing required modalities and insufficient independent lineages are surfaced.
- Structural multimodal verification must not be described as semantic cross-modal entailment until that capability is independently implemented and evaluated.

### Identity-preserving visual restoration assurance

- All detected faces are locked by the plan when identity preservation is requested.
- Plan integrity is recomputed at evaluation time.
- Identity similarity, landmark drift, face-region SSIM, geometry scale drift and rotation drift are threshold-gated.
- Super-resolution and background-removal requests have dimension/alpha constraints.
- Difference-map and metric-model hashes are bound to the evaluation receipt.
- Native restoration/face-metric models are not claimed unless separately integrated and qualified.

### Signed action finalization

- Only complete, integrity-verified V12 action chains can be finalized.
- The finalization envelope is signed/encrypted and bound to workspace, chain head and chain receipt.
- Verification reopens the envelope and rechecks the current chain state.

### Failure/regression memory

- Repeat failures use stable fingerprints.
- Resolution binds root cause, remediation, regression test and fix commit.
- A previously fixed fingerprint observed again becomes REGRESSION.
- Unresolved High/Critical OPEN or REGRESSION failures block the V15 release gate.

## C. External validation completion gate

V15 is **not independently validated** until an external assessor, independent of the implementation decision authority for the evaluated scope, produces attributable evidence tied to a frozen release. Minimum evidence:

- assessor identity and independence/conflict disclosure;
- exact tested commit SHA, deployment ID and configuration fingerprint;
- dated methodology and scope;
- validation dataset/case-set fingerprint and aggregate counts;
- primary metric results with confusion/count tables and confidence intervals where sampling applies;
- independent penetration test report with zero unresolved Critical findings and no unresolved High finding except explicitly documented risk acceptance;
- independent cryptographic review of custom binding/signature/key-management constructions;
- retest evidence for remediated Critical/High findings;
- documented limitations, exclusions and protocol deviations;
- signed/final report or otherwise verifiable attributable artifact.

If an organization materially develops the evaluated controls, the independent validation decision must be separated by personnel/governance and disclosed, or a second independent assessor must be used.

## D. Claim boundary

Internal PASS proves only that the repository-controlled gates for the exact candidate completed successfully. External PASS proves only what the external report actually assessed. Neither state establishes AGI, perfect factuality, universal security, regulatory certification, or safety outside the tested scope.
