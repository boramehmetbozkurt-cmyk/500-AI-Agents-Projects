"""Cover the documented `cp .env.example .env` configuration path.

python-dotenv was a declared dependency and both README.md and DEPLOYMENT.md tell
operators to create a .env, but nothing read it, so a local run silently ignored
every value in that file.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import config
from config import ENV_FILE, load_env_file

KEY = "ORBYTHRA_TEST_ENV_FILE_KEY"


@pytest.fixture
def clean_key():
    """Hand back a variable name that is absent now and restored afterwards.

    load_env_file writes to the real os.environ, which monkeypatch cannot undo
    because it never saw the assignment.
    """
    previous = os.environ.pop(KEY, None)
    try:
        yield KEY
    finally:
        if previous is None:
            os.environ.pop(KEY, None)
        else:
            os.environ[KEY] = previous


def test_env_file_is_anchored_to_the_package_not_the_working_directory():
    # Anchoring to the module keeps `uvicorn app:app` behaving identically whether
    # it is started from the repository root or from osiris_ai_fusion/.
    assert ENV_FILE == Path(config.__file__).resolve().parent / ".env"


def test_env_file_values_reach_the_environment(tmp_path, clean_key):
    env_file = tmp_path / ".env"
    env_file.write_text(f"{clean_key}=from-env-file\n", encoding="utf-8")

    load_env_file(env_file)

    assert os.environ[clean_key] == "from-env-file"


def test_real_environment_wins_over_the_env_file(tmp_path, clean_key):
    # Containers, CI and secret managers inject real variables. A stale .env left
    # in an image must never silently override them.
    os.environ[clean_key] = "from-real-environment"
    env_file = tmp_path / ".env"
    env_file.write_text(f"{clean_key}=from-env-file\n", encoding="utf-8")

    load_env_file(env_file)

    assert os.environ[clean_key] == "from-real-environment"


def test_missing_env_file_is_not_an_error(tmp_path, clean_key):
    # A deployment configured purely through real environment variables has no
    # .env at all, and importing config must still succeed.
    load_env_file(tmp_path / "does-not-exist.env")

    assert clean_key not in os.environ
