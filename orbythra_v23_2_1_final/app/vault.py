from __future__ import annotations

import json
from typing import Any

from app.config import SETTINGS
from app.crypto_core import CryptoConfigurationError, open_envelope, seal

_PREFIX = "orbenc1:"


class CryptoVault:
    @property
    def configured(self) -> bool:
        return SETTINGS.crypto_configured

    def _allow_plaintext_fallback(self) -> bool:
        return SETTINGS.environment in {"development", "test"}

    def encrypt_json(self, value: Any, *, workspace_id: str, purpose: str) -> str:
        if not self.configured:
            if self._allow_plaintext_fallback():
                return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
            raise CryptoConfigurationError("at_rest_encryption_not_configured")
        envelope = seal(
            payload={"value": value},
            intent={"action": "store", "asset": purpose, "recipient": workspace_id},
            effect={"action": "store", "asset": purpose, "recipient": workspace_id},
            approvals=[],
            min_approvals=0,
            workspace_id=workspace_id,
            domain=f"at-rest:{purpose}",
            ttl_seconds=0,
        )
        return _PREFIX + json.dumps(envelope, separators=(",", ":"), sort_keys=True)

    def decrypt_json(self, value: str, *, workspace_id: str, purpose: str) -> Any:
        if not value.startswith(_PREFIX):
            return json.loads(value or "null")
        if not self.configured:
            raise CryptoConfigurationError("at_rest_encryption_key_unavailable")
        envelope = json.loads(value[len(_PREFIX):])
        opened = open_envelope(envelope, expected_workspace_id=workspace_id)
        return opened["content"]["payload"]["value"]


VAULT = CryptoVault()
