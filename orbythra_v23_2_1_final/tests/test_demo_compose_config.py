from pathlib import Path

from app.config import _parse_api_keys, _parse_master_keys, _parse_roles


def _compose_value(name: str) -> str:
    for line in Path("docker-compose.demo.yml").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        prefix = f"{name}:"
        if stripped.startswith(prefix):
            return stripped[len(prefix):].strip().strip('"').strip("'")
    raise AssertionError(f"{name} not found in docker-compose.demo.yml")


def test_demo_compose_auth_and_crypto_are_parseable() -> None:
    api_keys = _parse_api_keys(_compose_value("ORBYTHRA_API_KEYS"))
    roles = _parse_roles(_compose_value("ORBYTHRA_API_ROLES"))
    master_keys = _parse_master_keys(_compose_value("ORBYTHRA_MASTER_KEYS"), "")

    assert api_keys == (("demo", "orbythra-demo-local-key-change-before-sharing"),)
    assert roles == (("demo", "admin"),)
    assert master_keys == (("demo-master", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"),)
