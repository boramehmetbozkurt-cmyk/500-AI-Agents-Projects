from __future__ import annotations

import ast
import json
import math
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from config import get_settings
from llm import ModelRouter
from osiris_client import READ_ONLY_TOOLS, OsirisClient
from provenance import make_evidence_record


@dataclass(frozen=True)
class CapabilitySpec:
    name: str
    domain: str
    description: str
    kind: str
    read_only: bool = True
    auto_execute: bool = True
    url_env: str | None = None
    api_key_env: str | None = None
    keywords: tuple[str, ...] = ()
    provider: str = "internal"


BUILTIN_CAPABILITIES: dict[str, CapabilitySpec] = {
    "web_search": CapabilitySpec(
        name="web_search",
        domain="general_research",
        description="General public-web research connector for factual topics not covered by OSIRIS-native feeds.",
        kind="http_json",
        url_env="FUSION_WEB_SEARCH_URL",
        api_key_env="FUSION_WEB_SEARCH_API_KEY",
        keywords=("latest", "today", "bugün", "current", "güncel", "who is", "kimdir", "price", "fiyat"),
        provider="configured_web_search",
    ),
    "sports_research": CapabilitySpec(
        name="sports_research",
        domain="sports",
        description="Read-only sports fixtures, form, injuries/news, metrics and prediction evidence connector.",
        kind="http_json",
        url_env="FUSION_SPORTS_URL",
        api_key_env="FUSION_SPORTS_API_KEY",
        keywords=("maç", "skor", "futbol", "basketbol", "fixture", "match", "score", "odds", "xg", "form"),
        provider="configured_sports",
    ),
    "calculator": CapabilitySpec(
        name="calculator",
        domain="calculation",
        description="Deterministic local arithmetic evaluator with no network access.",
        kind="local_calculator",
        keywords=("hesapla", "kaç eder", "calculate", "+", "-", "*", "/", "%"),
        provider="local",
    ),
    "direct_reasoning": CapabilitySpec(
        name="direct_reasoning",
        domain="general",
        description="Local/fallback model reasoning for non-time-sensitive, non-evidence tasks such as drafting, rewriting and ideation.",
        kind="local_model",
        keywords=("yaz", "rewrite", "çevir", "translate", "özetle", "summarize", "fikir", "idea", "prompt"),
        provider="model_router",
    ),
}


CURRENTNESS_TERMS = {
    "bugün", "şimdi", "güncel", "son dakika", "latest", "today", "now", "current",
    "canlı", "live", "fiyat", "price", "skor", "score", "hava", "weather", "near me",
}


def _manifest_dir() -> Path:
    configured = os.getenv("FUSION_CAPABILITY_DIR", "").strip()
    return Path(configured) if configured else Path(__file__).resolve().parent / "capability_manifests"


def _load_manifests() -> dict[str, CapabilitySpec]:
    specs: dict[str, CapabilitySpec] = {}
    directory = _manifest_dir()
    if not directory.exists():
        return specs
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            spec = CapabilitySpec(
                name=str(payload["name"]).strip().lower(),
                domain=str(payload.get("domain", "custom")),
                description=str(payload.get("description", "Custom capability")),
                kind=str(payload.get("kind", "http_json")),
                read_only=bool(payload.get("read_only", True)),
                auto_execute=bool(payload.get("auto_execute", True)),
                url_env=str(payload.get("url_env") or "") or None,
                api_key_env=str(payload.get("api_key_env") or "") or None,
                keywords=tuple(str(item).lower() for item in payload.get("keywords", [])),
                provider=str(payload.get("provider", "custom")),
            )
            if spec.name and re.fullmatch(r"[a-z0-9_]{2,64}", spec.name):
                specs[spec.name] = spec
        except (OSError, ValueError, TypeError, KeyError):
            continue
    return specs


def capability_specs() -> dict[str, CapabilitySpec]:
    specs = dict(BUILTIN_CAPABILITIES)
    specs.update(_load_manifests())
    return specs


def capability_ready(spec: CapabilitySpec) -> bool:
    if spec.kind in {"local_calculator", "local_model"}:
        return True
    if spec.kind == "http_json":
        return bool(spec.url_env and os.getenv(spec.url_env, "").strip())
    return False


def auto_tool_names() -> set[str]:
    names = set(READ_ONLY_TOOLS)
    for name, spec in capability_specs().items():
        if spec.read_only and spec.auto_execute and capability_ready(spec):
            names.add(name)
    return names


def capability_catalog() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in sorted(READ_ONLY_TOOLS):
        rows.append({
            "name": name,
            "domain": "osiris_native",
            "kind": "osiris_native",
            "read_only": True,
            "auto_execute": True,
            "ready": True,
            "provider": "osiris",
            "description": "Native OSIRIS passive data feed.",
        })
    for spec in sorted(capability_specs().values(), key=lambda item: item.name):
        row = asdict(spec)
        row["ready"] = capability_ready(spec)
        row["missing_configuration"] = [
            env_name
            for env_name in (spec.url_env,)
            if env_name and not os.getenv(env_name, "").strip()
        ]
        rows.append(row)
    return rows


def likely_requires_external_data(query: str) -> bool:
    q = query.lower()
    if any(term in q for term in CURRENTNESS_TERMS):
        return True
    if any(term in q for term in ("maç", "fixture", "injury", "sakat", "puan durumu", "standings")):
        return True
    return False


def infer_capability_names(query: str) -> list[str]:
    q = query.lower()
    selected: list[str] = []
    for name, spec in capability_specs().items():
        if any(keyword in q for keyword in spec.keywords):
            selected.append(name)
    return list(dict.fromkeys(selected))


def resolve_capability_gap(query: str, selected: list[str]) -> list[str]:
    gaps: list[str] = []
    specs = capability_specs()
    for name in selected:
        spec = specs.get(name)
        if spec and not capability_ready(spec):
            required = spec.url_env or "connector configuration"
            gaps.append(f"{name} requires {required}")
    if likely_requires_external_data(query) and not selected:
        web = specs["web_search"]
        if not capability_ready(web):
            gaps.append("fresh factual research requires FUSION_WEB_SEARCH_URL")
    return gaps


def _validate_connector_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme == "https":
        return
    if parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        return
    raise PermissionError("Connector URL must use HTTPS, except localhost development endpoints")


def _safe_calc(expression: str) -> float | int:
    expression = expression.replace("^", "**")
    tree = ast.parse(expression, mode="eval")
    allowed_bin = {
        ast.Add: lambda a, b: a + b,
        ast.Sub: lambda a, b: a - b,
        ast.Mult: lambda a, b: a * b,
        ast.Div: lambda a, b: a / b,
        ast.FloorDiv: lambda a, b: a // b,
        ast.Mod: lambda a, b: a % b,
        ast.Pow: lambda a, b: a**b,
    }
    allowed_unary = {ast.UAdd: lambda a: a, ast.USub: lambda a: -a}

    def visit(node: ast.AST) -> float | int:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in allowed_bin:
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow) and abs(float(right)) > 12:
                raise ValueError("Exponent is outside the safe calculator range")
            return allowed_bin[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in allowed_unary:
            return allowed_unary[type(node.op)](visit(node.operand))
        raise ValueError("Unsupported calculator expression")

    result = visit(tree)
    if isinstance(result, float) and not math.isfinite(result):
        raise ValueError("Non-finite calculator result")
    return result


def _calculator_expression(query: str) -> str:
    match = re.search(r"[-+*/%().\d\s^]{3,}", query)
    if not match:
        raise ValueError("No arithmetic expression found")
    return match.group(0).strip()


class UniversalToolClient:
    """Dispatches sealed read-only tools without accepting user-supplied URLs.

    Native OSIRIS tools use OsirisClient. Additional capabilities are either local
    deterministic/model tools or administrator-configured HTTPS JSON connectors.
    Connector endpoints and credentials can only come from environment variables or
    trusted on-disk manifests, which prevents a user query from becoming an SSRF URL.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.timeout = settings.tool_timeout_seconds
        self.max_response_bytes = settings.max_evidence_bytes
        self._osiris: OsirisClient | None = None

    async def __aenter__(self) -> "UniversalToolClient":
        self._osiris = OsirisClient()
        await self._osiris.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._osiris is not None:
            await self._osiris.__aexit__(exc_type, exc, tb)
            self._osiris = None

    async def fetch_tool(self, tool: str, *, query: str, scope: dict[str, Any]) -> dict[str, Any]:
        if tool in READ_ONLY_TOOLS:
            if self._osiris is None:
                raise RuntimeError("UniversalToolClient must be used as an async context manager")
            return await self._osiris.fetch_tool(tool)

        spec = capability_specs().get(tool)
        if spec is None or not spec.read_only or not spec.auto_execute:
            raise PermissionError(f"Capability is not authorized for autonomous read-only execution: {tool}")
        if not capability_ready(spec):
            return make_evidence_record(
                tool=tool,
                source_url=f"capability://{tool}",
                error=f"Capability is not configured; set {spec.url_env or 'required connector settings'}",
            )

        if spec.kind == "local_calculator":
            expression = _calculator_expression(query)
            data = {"expression": expression, "result": _safe_calc(expression)}
            return make_evidence_record(tool=tool, source_url="local://calculator", data=data)

        if spec.kind == "local_model":
            system = (
                "You are a general-purpose assistant operating as a bounded OSIRIS Fusion capability. "
                "Do not claim fresh facts without evidence. Perform only the requested drafting, transformation, "
                "reasoning or ideation task."
            )
            result = await ModelRouter().generate(system, query)
            data = {"text": result.text, "provider": result.provider, "model": result.model}
            return make_evidence_record(tool=tool, source_url="model://router", data=data)

        if spec.kind == "http_json":
            assert spec.url_env is not None
            url = os.getenv(spec.url_env, "").strip()
            _validate_connector_url(url)
            headers = {"User-Agent": "OSIRIS-Fusion/1.1 read-only connector"}
            if spec.api_key_env:
                api_key = os.getenv(spec.api_key_env, "").strip()
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
            payload = {"query": query, "scope": scope, "mode": "read_only"}
            try:
                async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False) as client:
                    response = await client.post(url, json=payload, headers=headers)
                    response.raise_for_status()
                    content = response.content
                    if len(content) > self.max_response_bytes:
                        raise ValueError("Connector response exceeds configured evidence limit")
                    content_type = response.headers.get("content-type", "")
                    if "json" not in content_type.lower() and content.strip()[:1] not in {b"{", b"["}:
                        raise ValueError("Connector returned non-JSON content")
                    data = response.json()
                return make_evidence_record(tool=tool, source_url=url, data=data)
            except Exception as exc:
                return make_evidence_record(
                    tool=tool,
                    source_url=url,
                    error=f"{type(exc).__name__}: {exc}",
                )

        raise PermissionError(f"Unsupported capability kind: {spec.kind}")
