from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path


def backup(destination: str) -> str:
    target = Path(destination).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    database_url = os.getenv("ORBYTHRA_DATABASE_URL", "").strip()
    if database_url.startswith(("postgresql://", "postgres://")):
        command = ["pg_dump", "--format=custom", "--file", str(target), database_url]
        subprocess.run(command, check=True)
        return str(target)

    source = Path(os.getenv("ORBYTHRA_DB_PATH", "./data/orbythra.db")).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    return str(target)


if __name__ == "__main__":
    output = sys.argv[1] if len(sys.argv) > 1 else "./backups/orbythra-backup.db"
    print(backup(output))
