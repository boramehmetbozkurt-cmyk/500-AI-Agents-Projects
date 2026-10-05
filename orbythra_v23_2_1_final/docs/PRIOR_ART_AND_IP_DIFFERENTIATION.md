# ORBYTHRA Prior-Art & IP Differentiation Working Dossier

Status: internal technical/legal-preparation material only. This is **not** a patentability opinion, freedom-to-operate opinion, ownership opinion, or legal clearance. Patent counsel must independently search, construe claims and assess jurisdiction-specific filing/disclosure issues.

## Purpose

The goal is to separate:

1. known/public building blocks that ORBYTHRA must not claim as inventions;
2. adjacent prior art that may constrain claim scope; and
3. candidate combinations/technical flows that may still justify counsel review.

## Known/public building blocks — do not claim alone

- AES-GCM, ChaCha20-Poly1305, HKDF, Ed25519, X25519, Argon2id and ordinary hashing/signature primitives;
- generic LLM gateways, model routing, rate limits, RBAC, OIDC/JWT SSO and tenant isolation;
- generic hallucination detection, attribution, grounding, RAG, benchmark/evaluator workflows;
- generic audit logging, consent, retention, erasure and privacy workflows;
- generic transaction signing, nonces, replay defense and approval thresholds.

ORBYTHRA value must be framed around specific system composition, control flow, semantic bindings, deterministic gates, evidence structures and operational implementation—not ownership of these public primitives.

## Material adjacent prior art identified in preliminary search

### A. LLM verification / hallucination identification

- US20250068667A1 / WO2025048994A1 — *Identifying hallucinations in large language model output*. Describes generating verification data for an LLM query result and processing it to determine whether a result was validly derived from input data. Priority/publication family should be reviewed carefully against ORBYTHRA evidence verification claims.
  - https://patents.google.com/patent/US20250068667A1/en
  - https://patents.google.com/patent/WO2025048994A1/en

- US20240296295A1 — *Attribution verification for answers and summaries generated from large language models*. Focuses on whether generated answers/summaries are substantiated by source documents.
  - https://patents.google.com/patent/US20240296295A1/en

- WO2026053006A1 — *Explainer, output verification, and hallucination correction for output of large language models*. Uses attribution links/text spans to identify hallucination candidates; claims priority to 2024-09-03.
  - https://patents.google.com/patent/WO2026053006A1/en

**Implication:** broad claims such as “verify LLM output against evidence” are crowded. Counsel should focus on ORBYTHRA's deterministic evidence-state transition, fail-closed disposition, engineering envelope, enterprise policy coupling, and downstream intent/effect binding if those combinations are sufficiently novel/non-obvious.

### B. Cryptographic transaction authorization / auditability

- EP3659085B1 — Mastercard, *transaction processing with complete cryptographic auditability*, priority 2017-07-25. Uses a moderating system and cryptographic/blockchain auditability for transactions.
  - https://patents.google.com/patent/EP3659085B1/en

- WO2022005638A1 — Mastercard, *Authorization data processing for multiple issuers*, priority 2020-06-30. Addresses validating authorization data and detecting alteration/reuse.
  - https://patents.google.com/patent/WO2022005638A1

- WO2026024864A1 — *Know your model and know your data systems and methods for transactions*. Describes AI-driven transacting agents and cryptographically verifiable consent tokens for wallet authority.
  - https://patents.google.com/patent/WO2026024864A1/en

- US20250238787A1 — *Systems and methods for digital identity and account abstraction*. Includes user operations based on user intention, verifiable credentials and signed operations in smart-account transaction flows.
  - https://patents.google.com/patent/US20250238787A1/en

**Implication:** broad claims such as “cryptographically prove user authorization/intention” are also crowded. ORBYTHRA counsel review should narrow to the exact semantic/technical sequence and data structures used to bind normalized canonical intent, effect fields, approval evidence, AEAD envelope, replay state and signed outcome receipt.

## Candidate ORBYTHRA differentiation families for counsel review

### Family 1 — Evidence-to-action assurance chain

Candidate system composition:

`Claim -> Evidence State -> Deterministic Disposition -> Engineering Envelope -> Enterprise Policy -> Human Approval -> Canonical Intent -> Effect Comparison -> Cryptographic Envelope -> Replay Check -> Signed Outcome Receipt`

Potential differentiator is not any single stage; it is the enforced transition from epistemic verification to action authorization and post-action evidence.

### Family 2 — EffectSeal semantic binding

Candidate narrow technical points:

- normalized/canonical intent commitment;
- protected effect-field comparison before execution/acceptance;
- approval proof bound to the exact intent digest;
- fail-closed mismatch behavior;
- AEAD envelope with domain/workspace/key metadata in authenticated data;
- replay-state reservation; and
- signed outcome receipt re-binding the verified result to the original intent commitment.

### Family 3 — MorseGuard normalization before assurance/crypto

Candidate narrow technical point: bounded normalization/decoding is performed before commitment, policy and cryptographic verification so visually/semantically wrapped representations cannot produce a different committed intent after approval.

### Family 4 — Evidence-first guarded disposition + engineering envelope

Candidate combination:

- deterministic status classes for contradiction, insufficiency, staleness and low authority;
- unqualified `ANSWER` only when every claim passes the gate;
- engineering decision envelope that explicitly separates assumptions, unknowns, required evidence, verification plan and FMEA prompts;
- same evidence state can be consumed by enterprise risk policy before provider/action execution.

### Family 5 — Cross-provider policy with assurance state

Candidate narrow combination: provider/region/data-retention/private-endpoint policy enforcement that additionally consumes evidence pass rate, guarded-claim count, risk tier and human approval before model/action invocation.

## Preliminary differentiation matrix

| Area | Prior art crowded? | ORBYTHRA candidate differentiation | Current confidence |
|---|---|---|---|
| Generic LLM hallucination detection | High | Do not claim broadly | Low |
| Generic evidence attribution | High | Deterministic multi-state gate + downstream policy/action coupling | Medium |
| Generic signed transaction authorization | High | Do not claim broadly | Low |
| Generic nonce/replay protection | High | Do not claim broadly | Low |
| Canonical intent + protected effect binding + approval digest + signed outcome receipt | Adjacent art exists | Exact sequence/data binding may merit claim drafting | Medium |
| Evidence verification -> engineering envelope -> enterprise policy -> intent/effect crypto chain | Less directly matched in preliminary search | System-level combination | Medium-High, pending professional search |
| DSEL alone | Custom implementation but cryptographic novelty unproven | Treat primarily as defense-in-depth/trade secret unless counsel finds claimable implementation | Low-Medium |

## Evidence preservation checklist

For every candidate invention family preserve:

- earliest conception date and dated notes;
- Git commit SHAs and source snapshots;
- inventor/contributor names and assignments;
- diagrams and protocol/data schemas;
- failed alternatives and why they failed;
- benchmark/test evidence demonstrating technical effect;
- public disclosures, emails, presentations and NDA dates;
- third-party/open-source dependencies and licenses;
- exact difference from every material prior-art reference.

## Filing strategy questions for patent counsel

1. Which candidate families remain novel after a professional worldwide prior-art search?
2. Which combinations are non-obvious over LLM verification + transaction authorization references when combined by a skilled person?
3. Have any public disclosures affected filing options or grace periods by jurisdiction?
4. Which portions should remain trade secrets instead of being disclosed in patents?
5. Are there freedom-to-operate risks in production use even if ORBYTHRA obtains its own patents?
6. Should claims focus on method, system, computer-readable medium, protocol/data structure, or narrower control-plane implementations?

## External standards context

ORBYTHRA assurance documentation should map controls to, but not claim certification against, NIST AI RMF / NIST AI 600-1, OWASP GenAI/LLM risks and current NIST SP 800-63 federation/authentication guidance. Standards alignment is evidence of disciplined engineering, not patent novelty.

## Claim discipline

Until counsel issues an opinion, permitted language is:

> “ORBYTHRA contains candidate proprietary inventions and an internally documented differentiation architecture undergoing prior-art and legal review.”

Do **not** state “patented,” “patent-safe,” “freedom-to-operate cleared,” “world-first,” or “no prior art exists” without the corresponding external legal evidence.
