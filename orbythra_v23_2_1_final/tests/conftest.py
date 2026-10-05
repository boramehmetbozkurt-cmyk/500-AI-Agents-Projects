from __future__ import annotations

import os
import subprocess
from pathlib import Path

if "ORBYTHRA_RELEASE_SHA" not in os.environ:
    try:
        os.environ["ORBYTHRA_RELEASE_SHA"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        os.environ["ORBYTHRA_RELEASE_SHA"] = "0" * 40

os.environ["ORBYTHRA_ENV"] = "test"
os.environ["ORBYTHRA_API_KEYS"] = "tester:test-secret,other:other-secret"
os.environ["ORBYTHRA_API_ROLES"] = "tester=admin,other=viewer"
os.environ["ORBYTHRA_DB_PATH"] = "/tmp/orbythra-fastapi-tests.db"
os.environ.pop("ORBYTHRA_DATABASE_URL", None)
os.environ["ORBYTHRA_RATE_LIMIT_PER_MINUTE"] = "100"
os.environ["ORBYTHRA_MASTER_KEYS"] = "v1:MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA"
os.environ["ORBYTHRA_CRYPTO_ALGORITHM"] = "aes256-gcm"
os.environ["ORBYTHRA_CRYPTO_DEFAULT_TTL_SECONDS"] = "3600"
os.environ["ORBYTHRA_CRYPTO_MAX_TTL_SECONDS"] = "86400"

Path(os.environ["ORBYTHRA_DB_PATH"]).unlink(missing_ok=True)
