# OSIRIS AI Fusion

**Evidence-first, authorization-aware AI-native OSINT research system.**

OSIRIS AI Fusion turns natural-language research questions into bounded, read-only investigations over
OSIRIS data sources. It plans tools, seals authority before execution, gathers evidence with provenance,
uses a local-first model for analysis, and returns a tamper-evident verification receipt.

## v0.4 live integration

The live integration layer is aligned with OSIRIS' documented passive public API contract. The canonical
flight tool uses `/api/flights`; the legacy `aircraft` tool name remains an alias for compatibility.
Documented passive feeds such as earthquakes, fires, weather, news, GDELT, satellites, maritime,
CCTV, markets and cyber-threat data can be registered for bounded research.

Traffic-producing `/api/scanner` and `/api/osint/sweep` routes are deliberately excluded from autonomous
execution. They cannot be selected through the read-only tool registry.

## Production-oriented capabilities

- LangGraph orchestration with explicit planner → collector → analyst → verifier stages.
- Read-only OSIRIS tool registry and hard exclusion of autonomous active scanning/exploitation.
- Live OSIRIS contract probe via authenticated `GET /osiris-contract`.
- Local-first Ollama model routing with optional OpenAI-compatible fallback.
- Per-source provenance records and SHA-256 evidence bundle binding.
- Availability-based source confidence metadata plus explicit analytical uncertainty.
- SEAL v2 canonical CBOR intent commitments.
- Short-lived nonce + persistent replay detection before tool execution.
- Tool allow-list, maximum tool-call budget and geo/time/case scope binding.
- Ed25519-signed receipts binding intent, evidence and analysis digests.
- Prompt-injection boundary treating external OSINT as untrusted data.
- API-key auth, single-process rate limiter, request IDs and security headers.
- Liveness/readiness endpoints and dependency degradation reporting.
- Response size limits, retry/backoff and bounded tool concurrency.
- Non-root Docker image, Compose development stack, unit tests and CI quality gates.
- Dependency audit and Docker build security gates on changes.
- Scheduled passive live smoke check against OSIRIS health/stats endpoints.
- Optional `smolagents` worker dependency kept outside the core runtime.

## Run

```bash
cd osiris_ai_fusion
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
ollama pull qwen2.5:7b
ollama serve
make check
uvicorn app:app --reload --port 8787
```

Example:

```bash
curl -X POST http://127.0.0.1:8787/investigate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $OSIRIS_FUSION_API_KEY" \
  -d '{
    "query":"İzmir ve Ege bölgesinde son 24 saatte olağandışı gelişmeleri araştır",
    "allowed_tools":["earthquakes","fires","flights","weather","news"],
    "scope":{"region":"Izmir, TR","time_range":"PT24H","case_id":"demo-001"}
  }'
```

Passive upstream smoke probe:

```bash
python scripts/live_smoke.py --base-url https://osirisai.live
```

## Production mode

Set:

```bash
APP_ENV=production
OSIRIS_FUSION_API_KEY=<strong-random-secret>
REQUIRE_SIGNED_RECEIPTS=true
SEAL_ED25519_PRIVATE_KEY_B64=<32-byte-raw-private-key-as-base64>
```

Do not commit production secrets. Put signing keys in a managed secret/KMS/HSM boundary.

## Release gates

A merge is expected to pass code linting, tests, bytecode compilation, DCO, Markdown linting,
Python dependency audit and a clean Docker build. The scheduled live smoke workflow is intentionally
separate from PR blocking because an external OSIRIS outage must not create a false code regression.

## Maturity definition

The repository can be made **10/10-ready**, but production maturity is not declared by code volume.
A true 10/10 release additionally requires deployment evidence: independent security review,
load/failure tests, KMS/HSM-backed key operations, backup/restore drills, direct OSIRIS UI integration,
and successful customer pilots. See `RUNBOOK.md` and `ARCHITECTURE.md`.

## Safety boundary

Automatic execution is limited to lawful/read-only OSINT. Active scanning, exploitation, credentials,
intrusive surveillance and face-recognition tracking are outside the autonomous registry.
