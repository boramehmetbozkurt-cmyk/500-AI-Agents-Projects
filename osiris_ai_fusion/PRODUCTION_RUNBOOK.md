# OSIRIS Production Runbook

This runbook describes a buyer-reproducible single-node deployment baseline for OSIRIS Fusion v1.3. It is intentionally conservative: external TLS termination, secret storage, monitoring and backups should be provided by the target infrastructure rather than embedded into source code.

## 1. Production boundary

The container listens on `127.0.0.1:8787` in the production Compose baseline. Put a TLS reverse proxy/load balancer in front of it. Do not expose the development service directly to the public Internet without TLS, access logging and infrastructure firewall policy.

Persistent state lives under `/data`:

- `/data/fusion.sqlite3`
- `/data/seal-replay.sqlite3`

The application filesystem is mounted read-only. `/tmp` is a bounded tmpfs.

## 2. Required secret/config inputs

Create `.env.production` outside source control. At minimum review/configure:

```text
SAAS_BASE_URL=https://your-domain.example
CORS_ORIGINS=https://your-domain.example
REQUEST_LIMIT_PER_MINUTE=30
WATCHER_ENABLED=true
WATCHER_POLL_SECONDS=300
REQUIRE_SIGNED_RECEIPTS=true
SEAL_ED25519_PRIVATE_KEY_B64=...

# Optional LLM/provider credentials
LLM_FALLBACK_BASE_URL=...
LLM_FALLBACK_API_KEY=...
LLM_FALLBACK_MODEL=...

# Billing only when all four are set
STRIPE_SECRET_KEY=...
STRIPE_WEBHOOK_SECRET=...
STRIPE_PRICE_PRO=...
STRIPE_PRICE_TEAM=...

# Explicitly licensed/configured commercial providers
LICENSED_PROVIDERS=...
```

Do not commit `.env.production`.

## 3. Start

```bash
docker compose -f docker-compose.production.yml build --pull
docker compose -f docker-compose.production.yml up -d
curl -fsS http://127.0.0.1:8787/health
```

Expected health flags include World, Temporal Reality Atlas, Sensor Mesh, Temporal Globe and Science Genome Graph.

## 4. Public product surfaces

- `/` — Public SaaS
- `/app` — Command Center
- `/atlas` — Fusion Atlas
- `/world-globe` — Temporal Globe
- `/science-explorer` — Science Genome Explorer
- `/docs` — FastAPI API reference (disable/restrict at the edge if desired for a private enterprise deployment)

## 5. Backup

Quiescing the application is not required for SQLite online backup because `ops_backup.py` uses the SQLite backup API. Backups should still be copied to encrypted off-host/object storage after creation.

Inside a maintenance environment with access to the data volume:

```bash
python ops_backup.py create /data/fusion.sqlite3 /secure-backups --label fusion
python ops_backup.py verify /secure-backups/<backup>.sqlite3
```

The backup manifest records SHA256, SQLite integrity status and table row counts.

Recommended policy:

- hourly local snapshots for 24 hours
- daily encrypted off-host copies for 30 days
- monthly retention according to customer/legal requirements
- regular restore drills, not backup creation alone

Do not retain customer data longer than contractual/privacy policy permits.

## 6. Restore drill

Restore to a new path first:

```bash
python ops_backup.py restore \
  /secure-backups/<backup>.sqlite3 \
  /restore-test/fusion.sqlite3
```

Then verify:

```bash
python ops_backup.py verify /secure-backups/<backup>.sqlite3
sqlite3 /restore-test/fusion.sqlite3 'PRAGMA integrity_check;'
```

Only replace production state after an incident owner approves the restore point. Keep the pre-restore database as an incident artifact unless privacy/deletion policy requires otherwise.

## 7. Science/genome bulk imports

For material imports use official source snapshots/dumps rather than attempting to crawl entire providers through public APIs.

Example normalized JSONL import:

```bash
python science_importer.py \
  --kind openalex_authors \
  --path /imports/openalex-authors.jsonl.gz \
  --release 2026-09 \
  --workspace reference \
  --expected-sha256 <sha256>
```

The importer records source checksum/release and resumes by checkpoint. After ingesting tenant data, `/science/graph/rebuild` derives relationships and automatically bridges public-reference science claims into OSIRIS World with digest-based duplicate suppression.

Do not import personal VCF/BAM/CRAM/FASTQ or identifiable patient genetics into the shared Science Genome Graph.

## 8. Pre-deploy smoke checks

```bash
python -m pip install -r requirements-dev.txt
ruff check .
pytest -q
python -m compileall -q .
python -c "import app; assert app.app.version == '1.3.0'"
python scripts/build_buyer_artifacts.py --output dist/buyer-dataroom
python ops_benchmark.py --scientists 250 --works 250 --output dist/buyer-dataroom/benchmark.json
```

The synthetic benchmark is a regression/reproducibility artifact, not a production SLA.

## 9. Monitoring baseline

Monitor at minimum:

- `/health` availability
- HTTP 5xx/429 rate
- investigation completion/error rate
- provider error/timeout rate
- latency percentiles at the reverse proxy/APM layer
- disk utilization and SQLite backup success
- watchlist lag
- Sensor Mesh failed receipts
- science import checkpoint failures
- unexpected growth in World/Science tables
- billing/webhook failures when Stripe is enabled

Current `/metrics` access requires an authenticated administrator context. A production deployment should scrape through an internal network or trusted service identity.

## 10. Incident response priorities

Immediately isolate/rotate credentials for:

- cross-tenant exposure
- secret/API-key leak
- unauthorized write/action behavior
- canonical World tampering
- personal genomic data in shared graph

Preserve request IDs, receipt IDs, logs, import manifests and database backup hashes for investigation.

See `THREAT_MODEL.md` for the full threat register.

## 11. Release / buyer evidence

Every release candidate should have successful:

- OSIRIS AI Fusion CI
- OSIRIS AI Fusion Security
- DCO
- Markdown Lint
- OSIRIS Asset Readiness

The Asset Readiness workflow emits a buyer data-room artifact containing file hashes, data-rights registry, resolved Python package inventory/SPDX document and a reproducible synthetic benchmark.

## 12. Gates that source code cannot self-certify

Before representing the system as enterprise/strategic-acquisition ready, obtain external evidence for:

- independent penetration test
- legal review of final IP/license schedule
- production uptime history
- design-partner/paid-pilot references
- production restore drill
- privacy/DPA review where personal/customer data is processed

These gates must not be marked completed merely because a source file or checklist exists.
