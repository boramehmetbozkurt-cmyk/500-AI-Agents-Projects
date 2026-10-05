# ORBYTHRA V15.0 Final Hardening

V15 is the repository-controlled final-hardening layer built on the green V12 assurance baseline. It is designed to close high-value internal gaps while keeping externally dependent claims explicitly pending.

## New V15 controls

### 1. Empirical calibration

`app/calibration_v15.py` records labeled confidence outcomes per workspace/domain/task and reports Brier score, expected calibration error and reliability bins. Adjustment is conservative: when sample size is insufficient the raw probability is returned unchanged.

### 2. Execution-time agent control

`app/agent_control_plane_v15.py` adds per-agent ACTIVE/SUSPENDED/KILLED state, workspace emergency stop, policy epochs, tool/operation capabilities, risk ceilings and expiry. `app/agent_execution.py` enforces this immediately before the existing V2 cryptographic authorization check, so a previously issued authorization cannot bypass a later kill/suspend decision.

### 3. Independently observed effect verification

`app/effect_verification_v15.py` verifies supplied observations against the action's previously committed intended-effect digest. One vote is counted per source lineage. Stale/future observations fail closed or produce an inconclusive result. High/Critical actions can require a V12 distributed-validator quorum bound to the observation manifest.

This is observation verification, not native physical sensing.

### 4. Multimodal evidence provenance

`app/multimodal_evidence_v15.py` creates deterministic manifests for text, image, audio, video, document, sensor and structured-data artifacts. It binds content/metadata hashes, provenance lineage, acquisition/capture time and claim coverage, and surfaces duplicate-content groups.

This layer does not claim semantic image/audio/video entailment yet.

### 5. Identity-preserving visual restoration assurance

`app/visual_identity_assurance_v15.py` turns restoration requests into immutable plans that lock all detected faces and forbid face reconstruction/beautification. The output gate can consume a declared metric adapter's measurements for identity embedding similarity, landmark drift, face-region SSIM, geometry scale, rotation and aspect-ratio drift. Difference-map/model hashes and background-alpha status are bound to the receipt.

This is the assurance/control layer for face-preserving restoration. Native restoration, segmentation and face-metric model execution remain adapter capabilities and must be integrated and evaluated separately.

### 6. Signed action-chain finalization

`app/action_chain_finalization_v15.py` signs/encrypts a completed V12 action chain finalization using the existing EffectSeal cryptographic layer. The finalization is bound to workspace, chain head and chain receipt and is re-verifiable against current chain state.

### 7. Persistent failure memory

`app/failure_memory_v15.py` gives recurring failures a stable fingerprint and tracks OPEN/FIXED/REGRESSION state. A fix must bind root cause, remediation, regression-test reference and fix commit. Reappearance of a fixed fingerprint automatically becomes REGRESSION. High/Critical unresolved records block the release gate.

## Production composition

All V15 routers are included in `app/api.py`. The pre-existing V2 agent execution endpoint remains the authoritative execution boundary, now with V15 control-plane enforcement layered before action execution.

## Test strategy

`tests/test_v15_final_hardening.py` exercises calibration drift, kill-switch/emergency enforcement, effect consensus, high-risk quorum requirements, multimodal provenance, visual identity pass/reject behavior, signed action finalization and failure-regression reopening.

The complete repository CI remains the qualification gate. V15 must preserve the full V12/V11/V10/... regression stack; a V15-only pass is insufficient.

## External dependencies that code alone cannot close

The following remain external evidence gates rather than repository TODOs:

- independent engineering validation;
- independent penetration test;
- scoped independent cryptographic review;
- real customer pilot/production workload history;
- real media/restoration adapter qualification;
- real external-world observation/sensor integration;
- independent semantic multimodal benchmark if semantic cross-modal claims are made.

ORBYTHRA must report those items as PENDING until attributable evidence exists.
