from __future__ import annotations

import base64
import re
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from fastapi.testclient import TestClient

from app.api import app


AUTH_HEADERS = {"X-API-Key": "test-secret"}
_PATH_PARAM_RE = re.compile(r"\{([^}]+)\}")


def _resolve(schema: dict[str, Any], document: dict[str, Any]) -> dict[str, Any]:
    ref = schema.get("$ref")
    if not ref:
        return schema
    node: Any = document
    for part in ref.removeprefix("#/").split("/"):
        node = node[part]
    return node


def _sample(schema: dict[str, Any] | None, document: dict[str, Any]) -> Any:
    if not schema:
        return None
    schema = _resolve(schema, document)

    if "const" in schema:
        return schema["const"]
    if "default" in schema:
        return schema["default"]
    if "example" in schema:
        return schema["example"]
    if schema.get("enum"):
        return schema["enum"][0]

    for union_key in ("oneOf", "anyOf"):
        if union_key in schema:
            choices = schema[union_key]
            non_null = [item for item in choices if _resolve(item, document).get("type") != "null"]
            return _sample((non_null or choices)[0], document)

    if "allOf" in schema:
        merged: dict[str, Any] = {}
        required: list[str] = []
        properties: dict[str, Any] = {}
        for item in schema["allOf"]:
            resolved = _resolve(item, document)
            properties.update(resolved.get("properties", {}))
            required.extend(resolved.get("required", []))
        if properties:
            merged["type"] = "object"
            merged["properties"] = properties
            merged["required"] = list(dict.fromkeys(required))
            return _sample(merged, document)
        return _sample(schema["allOf"][0], document)

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        schema_type = next((item for item in schema_type if item != "null"), "string")

    if schema_type == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        result = {name: _sample(properties[name], document) for name in required if name in properties}
        if not result and schema.get("additionalProperties"):
            value_schema = schema["additionalProperties"] if isinstance(schema["additionalProperties"], dict) else {"type": "string"}
            result["sample"] = _sample(value_schema, document)
        return result

    if schema_type == "array":
        minimum = int(schema.get("minItems", 0) or 0)
        return [_sample(schema.get("items", {}), document) for _ in range(max(1, minimum))]

    if schema_type == "integer":
        minimum = schema.get("minimum", 1)
        exclusive = schema.get("exclusiveMinimum")
        if isinstance(exclusive, (int, float)):
            minimum = max(minimum, exclusive + 1)
        return int(minimum)

    if schema_type == "number":
        minimum = schema.get("minimum", 0.5)
        exclusive = schema.get("exclusiveMinimum")
        if isinstance(exclusive, (int, float)):
            minimum = max(float(minimum), float(exclusive) + 0.5)
        return float(minimum)

    if schema_type == "boolean":
        return True

    if schema_type == "null":
        return None

    fmt = schema.get("format")
    if fmt == "date-time":
        return "2026-01-01T00:00:00Z"
    if fmt == "date":
        return "2026-01-01"
    if fmt == "uuid":
        return "00000000-0000-4000-8000-000000000001"
    if fmt in {"uri", "url"}:
        return "https://example.com/resource"
    if fmt == "email":
        return "endpoint-smoke@example.com"
    if fmt in {"binary", "byte"}:
        return "dGVzdA=="

    value = "sample"
    min_length = int(schema.get("minLength", 0) or 0)
    if len(value) < min_length:
        value += "x" * (min_length - len(value))
    return value


def _operation_request(path: str, method: str, operation: dict[str, Any], document: dict[str, Any], index: int) -> tuple[str, dict[str, Any]]:
    url = path
    params: dict[str, Any] = {}
    headers = {**AUTH_HEADERS, "X-Workspace-ID": f"smoke-{index}"}

    for parameter in operation.get("parameters", []):
        parameter = _resolve(parameter, document)
        name = parameter["name"]
        location = parameter["in"]
        value = _sample(parameter.get("schema", {}), document)
        if location == "path":
            url = url.replace("{" + name + "}", str(value))
        elif location == "query" and parameter.get("required"):
            params[name] = value
        elif location == "header" and parameter.get("required") and name.lower() not in {"x-api-key", "x-workspace-id"}:
            headers[name] = str(value)

    for name in _PATH_PARAM_RE.findall(url):
        url = url.replace("{" + name + "}", "sample")

    kwargs: dict[str, Any] = {"headers": headers, "params": params}
    request_body = operation.get("requestBody")
    if request_body:
        request_body = _resolve(request_body, document)
        content = request_body.get("content", {})
        if "application/json" in content:
            kwargs["json"] = _sample(content["application/json"].get("schema", {}), document)

    return url, kwargs


def test_every_registered_endpoint_is_http_safe_and_never_crashes() -> None:
    """Exercise every production API operation and reject uncontrolled server failures."""

    document = app.openapi()
    client = TestClient(app, raise_server_exceptions=False)
    failures: list[str] = []
    exercised: list[str] = []

    index = 0
    for path, path_item in sorted(document["paths"].items()):
        for method in ("get", "post", "put", "patch", "delete"):
            operation = path_item.get(method)
            if not operation:
                continue
            index += 1
            url, kwargs = _operation_request(path, method, operation, document, index)
            response = client.request(method.upper(), url, **kwargs)
            exercised.append(f"{method.upper()} {path} -> {response.status_code}")
            if response.status_code >= 500 and response.status_code != 503:
                failures.append(f"{method.upper()} {path} -> {response.status_code}: {response.text[:500]}")

    assert len(exercised) >= 90, f"unexpectedly low endpoint coverage: {len(exercised)}"
    assert not failures, "Unhandled endpoint failures:\n" + "\n".join(failures)


def test_core_liveness_and_readiness_are_healthy_in_configured_test_environment() -> None:
    client = TestClient(app, raise_server_exceptions=False)

    health = client.get("/health")
    assert health.status_code == 200, health.text
    assert health.json()["status"] == "ok"

    ready = client.get("/ready")
    assert ready.status_code == 200, ready.text
    payload = ready.json()
    assert payload["database_ready"] is True
    assert payload["auth_configured"] is True
    assert payload["ready"] is True, payload


def test_v9_validator_registration_has_working_success_and_validation_paths() -> None:
    client = TestClient(app, raise_server_exceptions=False)
    headers = {**AUTH_HEADERS, "X-Workspace-ID": "endpoint-v9"}

    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    public_key_b64 = base64.urlsafe_b64encode(public_key).decode().rstrip("=")

    valid = client.post(
        "/v9/trust/validators",
        headers=headers,
        json={
            "validator_id": "endpoint-contract-validator",
            "public_key_b64": public_key_b64,
            "organization": "endpoint-contract-org",
            "trust_weight": 1.0,
            "active": True,
        },
    )
    assert valid.status_code == 200, valid.text
    assert valid.json()["validator_id"] == "endpoint-contract-validator"
    assert len(valid.json()["fingerprint"]) == 64

    malformed = client.post(
        "/v9/trust/validators",
        headers=headers,
        json={
            "validator_id": "malformed-validator",
            "public_key_b64": "sample",
            "organization": "endpoint-contract-org",
        },
    )
    assert malformed.status_code == 400, malformed.text
    assert malformed.json()["detail"] == "invalid_ed25519_public_key"
