from __future__ import annotations

import re
import subprocess
from pathlib import Path

PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)(?:password|api[_-]?key|client[_-]?secret)\s*[=:]\s*['\"][^'\"]{16,}['\"]"),
]
EXCLUDED_PREFIXES = ("tests/", ".env.example", "docs/")


def main() -> int:
    files = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
    findings: list[str] = []
    for name in files:
        if name.startswith(EXCLUDED_PREFIXES):
            continue
        path = Path(name)
        if not path.is_file() or path.stat().st_size > 1_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in PATTERNS:
            if pattern.search(text):
                findings.append(f"potential secret: {name}")
                break
    if findings:
        print("\n".join(findings))
        return 1
    print("secret scan: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
