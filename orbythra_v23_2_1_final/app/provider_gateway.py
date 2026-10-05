from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any

from app.config import SETTINGS
from app.enterprise_models import ModelInvocationRequest, ProviderProfile

_SUPPORTED_DIRECT = {"openai", "mistral", "azure_openai", "anthropic", "google", "self_hosted", "generic"}


class ProviderGatewayError(RuntimeError):
    pass


@dataclass(frozen=True)
class PreparedProviderRequest:
    url: str
    headers: dict[str, str]
    payload: dict[str, Any]


class CircuitBreaker:
    def __init__(self) -> None:
        self._state: dict[str, tuple[int, float]] = {}
        self._lock = threading.RLock()

    def before_call(self, provider_id: str, now: float | None = None) -> None:
        current = time.monotonic() if now is None else now
        with self._lock:
            failures, open_until = self._state.get(provider_id, (0, 0.0))
            if open_until > current:
                raise ProviderGatewayError("provider_circuit_open")
            if open_until:
                self._state[provider_id] = (0, 0.0)

    def success(self, provider_id: str) -> None:
        with self._lock:
            self._state.pop(provider_id, None)

    def failure(self, provider_id: str, threshold: int, cooldown_seconds: int, now: float | None = None) -> None:
        current = time.monotonic() if now is None else now
        with self._lock:
            failures, _ = self._state.get(provider_id, (0, 0.0))
            failures += 1
            open_until = current + cooldown_seconds if failures >= threshold else 0.0
            self._state[provider_id] = (failures, open_until)

    def reset(self) -> None:
        with self._lock:
            self._state.clear()


CIRCUIT_BREAKER = CircuitBreaker()


def provider_secret_env(provider_id: str) -> str:
    suffix = re.sub(r"[^A-Za-z0-9]", "_", provider_id).upper()
    return f"ORBYTHRA_PROVIDER_{suffix}_TOKEN"


def _base_url(profile: ProviderProfile) -> str:
    if profile.base_url is None:
        raise ProviderGatewayError("provider_base_url_not_configured")
    return str(profile.base_url).rstrip("/")


def _assert_safe_remote_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ({"https"} if SETTINGS.environment == "production" else {"https", "http"}):
        raise ProviderGatewayError("provider_url_scheme_not_allowed")
    host = (parsed.hostname or "").lower().strip(".")
    if not host or host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise ProviderGatewayError("provider_host_not_allowed")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal and (literal.is_private or literal.is_loopback or literal.is_link_local or literal.is_multicast or literal.is_reserved or literal.is_unspecified):
        raise ProviderGatewayError("provider_host_not_public")
    if SETTINGS.environment == "production":
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)}
        except OSError as exc:
            raise ProviderGatewayError("provider_dns_resolution_failed") from exc
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
                raise ProviderGatewayError("provider_dns_resolved_private_address")


def prepare_provider_request(profile: ProviderProfile, body: ModelInvocationRequest, token: str) -> PreparedProviderRequest:
    if not profile.enabled:
        raise ProviderGatewayError("provider_disabled")
    if profile.family not in _SUPPORTED_DIRECT:
        raise ProviderGatewayError("provider_family_requires_managed_adapter")
    if profile.model_ids and body.model_id not in profile.model_ids:
        raise ProviderGatewayError("model_not_allowlisted_for_provider")
    base = _base_url(profile)
    messages = [message.model_dump(mode="json") for message in body.messages]
    headers = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "ORBYTHRA-Provider-Gateway/1"}

    if profile.family in {"openai", "mistral", "self_hosted", "generic"}:
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return PreparedProviderRequest(url=f"{base}/v1/chat/completions", headers=headers, payload={"model": body.model_id, "messages": messages, "temperature": body.temperature, "max_tokens": body.max_tokens})
    if profile.family == "azure_openai":
        if not token:
            raise ProviderGatewayError("provider_secret_not_configured")
        headers["api-key"] = token
        version = urllib.parse.quote(profile.api_version or "2024-10-21", safe="")
        model = urllib.parse.quote(body.model_id, safe="")
        return PreparedProviderRequest(url=f"{base}/openai/deployments/{model}/chat/completions?api-version={version}", headers=headers, payload={"messages": messages, "temperature": body.temperature, "max_tokens": body.max_tokens})
    if profile.family == "anthropic":
        if not token:
            raise ProviderGatewayError("provider_secret_not_configured")
        headers["x-api-key"] = token
        headers["anthropic-version"] = profile.api_version or "2023-06-01"
        system_parts = [item.content for item in body.messages if item.role == "system"]
        non_system = [item.model_dump(mode="json") for item in body.messages if item.role != "system"]
        payload: dict[str, Any] = {"model": body.model_id, "messages": non_system, "temperature": body.temperature, "max_tokens": body.max_tokens}
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        return PreparedProviderRequest(url=f"{base}/v1/messages", headers=headers, payload=payload)
    if profile.family == "google":
        if not token:
            raise ProviderGatewayError("provider_secret_not_configured")
        headers["x-goog-api-key"] = token
        contents = [{"role": "model" if item.role == "assistant" else "user", "parts": [{"text": item.content}]} for item in body.messages if item.role != "system"]
        payload = {"contents": contents, "generationConfig": {"temperature": body.temperature, "maxOutputTokens": body.max_tokens}}
        system_parts = [item.content for item in body.messages if item.role == "system"]
        if system_parts:
            payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
        model = urllib.parse.quote(body.model_id, safe="-._")
        return PreparedProviderRequest(url=f"{base}/v1beta/models/{model}:generateContent", headers=headers, payload=payload)
    raise ProviderGatewayError("provider_family_not_supported")


def _post_json(prepared: PreparedProviderRequest, timeout: float = 30.0) -> dict[str, Any]:
    _assert_safe_remote_url(prepared.url)
    request = urllib.request.Request(prepared.url, data=json.dumps(prepared.payload, separators=(",", ":")).encode("utf-8"), headers=prepared.headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(5_000_001)
    except urllib.error.HTTPError as exc:
        raise ProviderGatewayError(f"provider_http_error:{exc.code}") from exc
    except Exception as exc:
        raise ProviderGatewayError("provider_transport_error") from exc
    if len(raw) > 5_000_000:
        raise ProviderGatewayError("provider_response_too_large")
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise ProviderGatewayError("provider_response_invalid_json") from exc
    if not isinstance(parsed, dict):
        raise ProviderGatewayError("provider_response_must_be_object")
    return parsed


def _retryable(exc: ProviderGatewayError) -> bool:
    value = str(exc)
    if value in {"provider_transport_error", "provider_dns_resolution_failed"}:
        return True
    if value.startswith("provider_http_error:"):
        try:
            code = int(value.rsplit(":", 1)[1])
        except ValueError:
            return False
        return code == 429 or 500 <= code <= 599
    return False


def extract_text(profile: ProviderProfile, response: dict[str, Any]) -> str:
    try:
        if profile.family in {"openai", "mistral", "azure_openai", "self_hosted", "generic"}:
            return str(response["choices"][0]["message"]["content"])
        if profile.family == "anthropic":
            blocks = response.get("content", [])
            text = "".join(str(block.get("text", "")) for block in blocks if isinstance(block, dict) and block.get("type") == "text")
            if text:
                return text
        if profile.family == "google":
            parts = response["candidates"][0]["content"]["parts"]
            text = "".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))
            if text:
                return text
    except (KeyError, IndexError, TypeError):
        pass
    raise ProviderGatewayError("provider_response_text_not_found")


def invoke_registered_model(profile: ProviderProfile, body: ModelInvocationRequest) -> tuple[str, str, float]:
    secret = os.getenv(provider_secret_env(profile.provider_id), "").strip()
    if profile.family not in {"self_hosted", "generic"} and not secret:
        raise ProviderGatewayError("provider_secret_not_configured")
    prepared = prepare_provider_request(profile, body, secret)
    CIRCUIT_BREAKER.before_call(profile.provider_id)
    reference = "inf_" + uuid.uuid4().hex[:20]
    started = time.perf_counter()
    attempts = profile.max_retries + 1
    last_error: ProviderGatewayError | None = None
    for attempt in range(attempts):
        try:
            response = _post_json(prepared, timeout=profile.timeout_seconds)
            text = extract_text(profile, response)
            CIRCUIT_BREAKER.success(profile.provider_id)
            return text, reference, (time.perf_counter() - started) * 1000.0
        except ProviderGatewayError as exc:
            last_error = exc
            CIRCUIT_BREAKER.failure(profile.provider_id, profile.circuit_breaker_threshold, profile.circuit_breaker_cooldown_seconds)
            if attempt >= attempts - 1 or not _retryable(exc):
                raise
            time.sleep(min(0.25 * (2 ** attempt), 1.0))
            CIRCUIT_BREAKER.before_call(profile.provider_id)
    raise last_error or ProviderGatewayError("provider_transport_error")
