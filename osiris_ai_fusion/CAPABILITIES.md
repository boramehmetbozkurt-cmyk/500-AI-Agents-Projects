# OSIRIS FUSION 1.2 — Provider Federation

OSIRIS FUSION does not hard-code one connector per question type. External research is routed through a domain-agnostic `provider_federation` capability that can rank and query multiple trusted read-only providers in parallel.

Sports is only one provider domain. It is not the center of the architecture and it is not a privileged autonomous tool.

## Routing model

```text
user query
  -> planner
  -> native OSIRIS passive feeds, when applicable
  -> provider_federation for external research
       -> rank matching providers
       -> fan out to up to FUSION_PROVIDER_FANOUT providers
       -> collect JSON evidence in parallel
       -> use general web only when no better provider is ready
  -> calculator for deterministic arithmetic
  -> direct_reasoning for non-fresh drafting / transformation / ideation
  -> capability_gap when required live data has no trusted provider
  -> evidence + analysis + SEAL effect verification + receipt
```

The fail-closed rule is deliberate. Missing live-data access must not be silently replaced by model memory or a fabricated answer.

## Provider domains

Configured provider profiles exist for:

- sports
- finance and market data
- crypto and blockchain
- news and current events
- science and academic research
- patents and intellectual property
- companies and business intelligence
- legal and regulation research
- real estate and property
- vehicles and automotive listings/data
- jobs and careers
- travel
- shopping and product research
- public social/forum research
- places, maps and local search
- general web research as a fallback

Any subset can be configured. The router discovers which providers are actually ready at runtime.

## Built-in live read-only providers

Fusion includes direct adapters for several public JSON APIs that do not require secrets:

- Turkish Wikipedia search
- OpenAlex scholarly works
- Crossref scholarly metadata
- OpenStreetMap Nominatim place search
- Hacker News search via Algolia

These providers are still subject to their own terms, attribution rules and rate limits. Being technically reachable does not grant redistribution or commercial rights.

## Multi-provider fan-out

`FUSION_PROVIDER_FANOUT` controls how many ranked providers a single external-research query may use in parallel. The default is 3 and the runtime clamps the value to a bounded range.

For example, an academic query can route to both OpenAlex and Crossref. A configured finance deployment can route to more than one finance provider. The result records the providers used and their source URLs so evidence remains traceable.

General web is not the single gateway for the whole product. It is the fallback when no more specific ready provider matches the query.

## Configured provider gateway contract

Administrator-configured provider gateways receive a read-only POST request:

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

They must return JSON. Responses should preserve original source URLs, timestamps, identifiers and attribution wherever applicable.

Example environment variables:

```text
FUSION_FINANCE_URL=https://your-finance-gateway.example/query
FUSION_FINANCE_API_KEY=...
FUSION_SPORTS_URL=https://your-sports-gateway.example/query
FUSION_SPORTS_API_KEY=...
FUSION_WEB_SEARCH_URL=https://your-general-search-gateway.example/query
FUSION_WEB_SEARCH_API_KEY=...
```

Provider URLs are administrator configuration, not prompt input. Production endpoints must use HTTPS; localhost development can use HTTP. Redirects are not followed and response size is bounded.

## Add providers without planner changes

Set `FUSION_PROVIDER_DIR` to a trusted local directory containing JSON provider manifests. A file can contain one provider, a list, or a `providers` array.

Example with two finance providers:

```json
{
  "providers": [
    {
      "provider_id": "finance_primary",
      "domains": ["finance", "markets"],
      "description": "Primary read-only market provider",
      "transport": "get_json",
      "url": "https://provider-a.example/search",
      "query_param": "q",
      "keywords": ["hisse", "stock", "ticker", "price"],
      "priority": 99,
      "read_only": true,
      "auto_execute": true
    },
    {
      "provider_id": "finance_secondary",
      "domains": ["finance", "markets"],
      "description": "Secondary read-only market provider",
      "transport": "get_json",
      "url": "https://provider-b.example/search",
      "query_param": "q",
      "keywords": ["hisse", "stock", "ticker", "price"],
      "priority": 95,
      "read_only": true,
      "auto_execute": true
    }
  ]
}
```

The manifest directory must be controlled by the deployment administrator. Manifests and execution URLs are never accepted from end-user prompts.

## Discovery API

`GET /providers` reports provider domains, readiness, configuration gaps, priority, attribution metadata and commercial-policy context.

`GET /capabilities` reports autonomous capabilities. External providers are intentionally hidden behind one `provider_federation` tool contract instead of creating a new planner tool for every data source.

`GET /capabilities/resolve?query=...` previews the selected capabilities, matching provider domains, provider route and capability gaps before execution.

## SEAL boundary

Every automatically executed path stays inside the same authorization boundary:

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

Adding a provider does not bypass authorization. Provider federation remains passive/read-only. Active scanning, exploitation, credential access, intrusive surveillance and facial tracking are outside the autonomous tool boundary.

## Action connectors are separate

A future connector that can send mail, edit records, make a purchase, publish content or cause another side effect must not be registered as an autonomous read-only provider. Actions require explicit user approval and a stricter SEAL effect policy.

## What “universal” means

Universal means new legitimate read-only knowledge sources can normally be connected once, described in the provider registry, and then discovered automatically. One query may use several providers rather than forcing all traffic through one service.

It does not mean Fusion has magical access to every private database or paid service. Services that require an account, API key, paid license or private connector still need legitimate access. When that access is absent, Fusion reports the provider gap instead of inventing data.
