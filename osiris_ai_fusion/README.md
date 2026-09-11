# OSIRIS AI Fusion

A read-only, multi-agent OSINT research layer designed to sit on top of OSIRIS.

## What it does

1. Accepts a natural-language investigation request.
2. Plans which OSIRIS read-only data tools are relevant.
3. Creates a SEAL intent envelope before data access.
4. Collects evidence from OSIRIS APIs in parallel.
5. Uses a free/local Ollama model for analysis by default.
6. Produces a verification receipt showing which tools were authorized and used.

## Current architecture

- **LangGraph**: stateful orchestration / multi-step agent graph.
- **Hugging Face smolagents**: installed as the lightweight specialist-agent layer for future tool agents and sandboxed code agents.
- **Ollama**: free local inference provider by default.
- **OSIRIS**: live read-only OSINT data source.
- **SEAL**: canonical intent + policy/effect verification layer.

## Safety boundary

The default registry contains only read-only OSINT endpoints. Active scanning, exploitation, credential access, intrusive surveillance and other offensive actions are intentionally excluded from autonomous execution.

## SEAL v0.1

The current implementation uses:

- Unicode NFC normalization
- deterministic canonical CBOR
- lowercase canonical field identifiers
- domain-separated SHA-256 intent commitments
- random nonce and short expiration window
- allow-listed tool execution
- effect receipt verification
- optional HMAC-SHA256 receipt authentication via `SEAL_MASTER_KEY_HEX`

SEAL does **not** replace audited encryption primitives. Encryption at rest/in transit should continue to use standard primitives and platform TLS/key-management facilities.

## Run locally

```bash
cd osiris_ai_fusion
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
ollama pull qwen2.5:7b
ollama serve
uvicorn app:app --reload --port 8787
```

Then:

```bash
curl -X POST http://127.0.0.1:8787/investigate \
  -H "Content-Type: application/json" \
  -d '{"query":"İzmir ve Ege bölgesinde son 24 saatte olağandışı gelişmeleri araştır"}'
```

## Next integration step

When the user's OSIRIS fork becomes available to the connected GitHub account, move this core into the fork and expose it through OSIRIS' Next.js UI as an AI search/command console. The OSIRIS map can then consume the returned evidence coordinates and activate matching layers.

## Planned specialist agents

- Geo Agent
- Seismic Agent
- Aviation Agent
- Fire / Disaster Agent
- Conflict / News Agent
- Cyber Threat (defensive/read-only) Agent
- Correlation Agent
- Evidence Verifier
- Report Agent

Each specialist must receive a SEAL-scoped tool allow-list. No agent gets unrestricted tool access.
