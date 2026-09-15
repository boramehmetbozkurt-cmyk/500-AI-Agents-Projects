from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "dist", "data"}
EXCLUDED_SUFFIXES = {".sqlite3", ".db", ".pyc", ".png", ".jpg", ".jpeg", ".gif", ".zip"}
FORBIDDEN_FILENAMES = {".env", ".env.production", ".env.local"}

PATTERNS = {
    "private_key_pem": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |ED25519 )?PRIVATE KEY-----"),
    "openai_key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "aws_access_key": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "stripe_live_secret": re.compile(r"\bsk_live_[A-Za-z0-9]{16,}\b"),
    "stripe_live_webhook": re.compile(r"\bwhsec_[A-Za-z0-9]{24,}\b"),
}


def text_files(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if path.suffix.lower() in EXCLUDED_SUFFIXES:
            continue
        yield path


def scan(root: Path = ROOT) -> list[str]:
    findings: list[str] = []
    for path in text_files(root):
        relative = path.relative_to(root).as_posix()
        if path.name in FORBIDDEN_FILENAMES:
            findings.append(f"forbidden secret file: {relative}")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for name, pattern in PATTERNS.items():
            match = pattern.search(text)
            if match:
                line = text.count("\n", 0, match.start()) + 1
                findings.append(f"{name}: {relative}:{line}")
    return findings


def main() -> None:
    parser = argparse.ArgumentParser(description="Fail if credential-like material exists in OSIRIS source")
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    findings = scan(Path(args.root))
    if findings:
        print("Potential secret material detected:", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        raise SystemExit(1)
    print("OSIRIS secret scan: clean")


if __name__ == "__main__":
    main()
