# ORBYTHRA Engineering Intelligence

ORBYTHRA Engineering Intelligence turns the supplied multi-layer engineering prompt into a product capability rather than leaving it as a loose prompt file.

## Purpose

The mode is designed for engineering, manufacturing, product-development and technical design problems that need first-principles reasoning, multi-scale analysis, explicit trade-offs and a measurable verification plan.

The canonical source prompt is stored unchanged at:

`prompts/engineering_system_v2_tr.md`

## Required reasoning surface

Every analysis is instructed to scan:

- scale: subatomic/quantum -> atom/bond -> molecule/polymer -> nano/virus -> cell/microbiology -> microstructure -> component -> system -> environment/lifetime
- disciplines: physics, chemistry, biology/microbiology, mathematics/geometry, materials, electronics/power, computing, GD&T, manufacturing and design
- modes: TOPRAK, SU, ATEŞ, HAVA
- decision protocol: measurable objective, first principles, constraints, scale scan, TRIZ contradiction, cross-domain analogy, at least two alternatives, decision, FMEA and verification

## API

### `GET /engineering`

Returns mode metadata and audit principles.

### `GET /engineering/prompt/meta`

Returns prompt version and structural requirements without exposing secrets or model configuration.

### `POST /engineering/analyze`

Input fields:

- `problem` (required)
- `target`
- `budget`
- `quantity`
- `operating_conditions`
- `lifetime`
- `standards[]`
- `manufacturing_capability`
- `constraints[]`
- `language`

The result includes the model/provider, answer and a structural audit. If required sections are missing, ORBYTHRA performs one bounded repair pass.

## Integrity rules

- Unknown measurements remain unknown/assumptions; they are not fabricated.
- Numerical values require units when the engineering response uses quantities.
- High-risk engineering must identify the need for authorized engineering approval where applicable.
- Model reasoning is not a certification or physical test result.
- The mode does not make ORBYTHRA an AGI; it creates a stronger, auditable engineering decision workflow.

## Future World bridge

Engineering results should only enter ORBYTHRA World after source/evidence validation. A model-generated engineering conclusion must not silently become a `fact`; it should enter as `belief` or sourced `claim` until verified by measurements, tests or authoritative evidence.
