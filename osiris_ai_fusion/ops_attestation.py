from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

DOMAIN = b"ORBYTHRA-RELEASE-ATTESTATION-V1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_sha() -> str:
    configured = os.getenv("GITHUB_SHA", "").strip()
    if configured:
        return configured
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sign(payload: dict[str, Any]) -> dict[str, Any]:
    raw_b64 = os.getenv("SEAL_ED25519_PRIVATE_KEY_B64", "").strip()
    if not raw_b64:
        return {
            "signed": False,
            "reason": "SEAL_ED25519_PRIVATE_KEY_B64 not configured",
            "algorithm": "Ed25519",
        }
    raw = base64.b64decode(raw_b64)
    if len(raw) != 32:
        raise ValueError("SEAL_ED25519_PRIVATE_KEY_B64 must decode to 32 raw bytes")
    private_key = Ed25519PrivateKey.from_private_bytes(raw)
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    canonical = _canonical(payload)
    framed = len(DOMAIN).to_bytes(8, "big") + DOMAIN + len(canonical).to_bytes(8, "big") + canonical
    signature = private_key.sign(framed)
    return {
        "signed": True,
        "algorithm": "Ed25519",
        "domain": DOMAIN.decode("ascii"),
        "public_key_b64": base64.b64encode(public_key).decode("ascii"),
        "signature_b64": base64.b64encode(signature).decode("ascii"),
    }


def build_attestation(paths: list[Path]) -> dict[str, Any]:
    files = []
    for path in sorted(paths, key=lambda item: item.as_posix()):
        if not path.is_file():
            raise FileNotFoundError(path)
        files.append(
            {
                "path": path.as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    subject = {
        "schema": "orbythra.release-attestation.v1",
        "product": "ORBYTHRA",
        "git_sha": _git_sha(),
        "generated_at": int(time.time()),
        "files": files,
    }
    subject["digest_sha256"] = hashlib.sha256(_canonical(subject)).hexdigest()
    return {"subject": subject, "signature": _sign(subject)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ORBYTHRA release provenance attestation")
    parser.add_argument("--output", required=True)
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    result = build_attestation([Path(value) for value in args.paths])
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
