# OSIRIS World

OSIRIS World is the verified living-world layer for OSIRIS Fusion. It turns evidence-first investigations into a temporal world state that can be queried as-of a past observation time, compared across valid-time states, and forked into counterfactual scenarios without contaminating observed reality.

## Core invariants

- The canonical branch is `reality`.
- `fact`, `claim`, `belief`, and `assumption` are separate statement kinds.
- A `fact` requires at least one evidence ID.
- New facts may only be asserted on the `reality` branch.
- An `assumption` may only be written to a fork branch.
- A fork inherits its parent only up to the fork observation time. Later changes in reality do not leak backward into that scenario.
- Every API operation is scoped to the authenticated SaaS tenant.
- `observed_at` is server-controlled through the public API. `valid_from` and `valid_to` model when a statement is true in the represented world.

## Reality Graph

World events may reference another entity through `object_entity_id`. Active relations are projected into `/world/graph` as nodes and evidence-status-aware edges.

Examples include:

- company A `acquired` company B
- country A `regulates` asset B
- person A `leads` company B
- technology A `depends_on` technology B

## Truth model

A state record exposes the statement classes independently instead of flattening them into one answer.

- `verified`: an evidence-bound fact is active.
- `verified_disputed`: a fact exists while active claims disagree with it.
- `claimed`: one or more claims agree and no fact is present.
- `contested`: active claims disagree and no fact resolves them.
- `belief_only`: OSIRIS has an explicit belief but no active claim or fact.
- `hypothetical`: a fork assumption overrides the inherited state.

This prevents model belief from silently becoming truth.

## Bitemporal Time Machine

World state has two clocks:

1. `observed_at`: when OSIRIS learned the information.
2. `valid_from` / `valid_to`: when the information is valid in the represented world.

`GET /world/state?observed_at=...&valid_at=...` can therefore answer questions such as what OSIRIS knew at a past time without leaking later knowledge into that snapshot.

## World Forks

`POST /world/forks` creates a branch from `reality` or from another fork. Counterfactual assumptions can then be written to the new branch and compared with reality using `/world/diff`.

A fork never mutates the canonical reality branch.

## World Pulse

`GET /world/pulse` compares the number of reality events in the current time window against the previous equal window, grouped by entity type. `change_score` is a simple velocity signal, not a causal or statistical proof. It is intended to identify categories that deserve deeper OSIRIS investigation.

## API

- `GET /world` — World capability and invariants.
- `POST /world/events` — append one tenant-scoped world event.
- `POST /world/events/batch` — append up to 100 structured events.
- `GET /world/state` — reconstruct bitemporal world state.
- `GET /world/graph` — project active entity relations.
- `POST /world/forks` — create a counterfactual branch.
- `GET /world/forks` — list reality and scenario branches.
- `GET /world/diff` — compare two branches.
- `GET /world/pulse` — detect unusual change velocity by entity type.

## Integration direction

Provider federation, Fusion investigations, Atlas maps, and specialist Hunter modules should write structured events through the World contract. They remain sensors; OSIRIS World is the shared state, provenance, time-travel, and scenario layer.

Wallet Hunter therefore remains a crypto-intelligence sensor rather than the primary product. The same contract can support future Market Hunter, Patent Hunter, Company Hunter, Domain Hunter, Research Hunter, and Opportunity Hunter modules.
