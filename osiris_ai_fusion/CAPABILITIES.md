# OSIRIS FUSION 1.1 — Universal Capabilities

OSIRIS FUSION does not try to hard-code every possible user question. It uses a capability router that chooses the smallest authorized read-only capability for each request.

## Routing order

1. Native OSIRIS passive feeds for supported OSINT domains.
2. A specialized configured connector, such as `sports_research`.
3. A general configured `web_search` connector for fresh public facts.
4. Local deterministic tools such as `calculator`.
5. `direct_reasoning` for non-fresh drafting, transformation, ideation and stable reasoning.
6. `capability_gap` when fresh/current facts require a connector that is not configured.

The last rule is deliberate. A missing live-data connector must never be silently replaced by model memory or a fabricated answer.

## Built-in extension points

### General web research

Configure once:

```text
FUSION_WEB_SEARCH_URL=https://your-trusted-search-connector.example/query
FUSION_WEB_SEARCH_API_KEY=...
```

### Sports research

Configure once:

```text
FUSION_SPORTS_URL=https://your-trusted-sports-connector.example/query
FUSION_SPORTS_API_KEY=...
```

The planner then discovers and selects these capabilities automatically when the query requires them.

## Connector contract

Read-only HTTP connectors receive a POST request:

```json
{
  "query": "user request",
  "scope": {
    "region": "optional",
    "time_range": "optional"
  },
  "mode": "read_only"
}
```

They must return a JSON object or array. When applicable, the response should preserve source URLs, timestamps and provider attribution so Fusion can bind the result into its evidence ledger.

Connector endpoints are administrator-configured. User prompts cannot supply arbitrary connector URLs. Production endpoints must use HTTPS; plain HTTP is accepted only for localhost development. Redirects are not followed and response size is bounded.

## Add a new domain without changing Python code

Set `FUSION_CAPABILITY_DIR` to a trusted local directory containing JSON manifests. Example:

```json
{
  "name": "patents_research",
  "domain": "patents",
  "description": "Read-only patent and filing research connector.",
  "kind": "http_json",
  "read_only": true,
  "auto_execute": true,
  "url_env": "FUSION_PATENTS_URL",
  "api_key_env": "FUSION_PATENTS_API_KEY",
  "keywords": ["patent", "patentler", "filing"],
  "provider": "your_patent_provider"
}
```

Then configure the endpoint as an environment variable. The manifest directory must be controlled by the deployment administrator; manifests are not accepted from end-user prompts.

## Capability discovery API

`GET /capabilities` reports all native and extension capabilities, their readiness and missing configuration.

`GET /capabilities/resolve?query=...` previews which capabilities the router would select and reports missing connectors before execution.

## SEAL boundary

Every automatically executed capability is still subject to the same SEAL flow:

```text
query
  -> capability plan
  -> sealed intent / allow-list / tool budget
  -> read-only execution
  -> evidence IDs + digest
  -> analysis
  -> effect verification
  -> receipt
```

Adding a connector does not bypass authorization. Only capabilities marked both `read_only=true` and `auto_execute=true` are eligible for autonomous execution.

## Actions are different

A future connector that can send mail, change records, make purchases, publish content or perform another side effect must not be registered as an autonomous read-only capability. Action connectors require a separate approval flow, explicit user authorization and a stricter SEAL effect policy.

## What “universal” means

Universal capability routing means a new read-only knowledge domain can normally be connected once and then discovered automatically, rather than requiring a new planner implementation for every question.

It does not mean the system has magical access to every private database or live service. A provider that requires an account, API key, license or private connector still has to be connected legitimately. Until then, Fusion reports the exact capability gap instead of inventing data.
