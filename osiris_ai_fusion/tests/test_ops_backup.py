import json
import sqlite3

from ops_backup import create_backup, restore_backup, verify_backup


def _db(path):
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE world_events_test(id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        conn.executemany(
            "INSERT INTO world_events_test(id, payload) VALUES (?, ?)",
            [("1", "alpha"), ("2", "beta")],
        )
        conn.commit()


def test_backup_verify_restore_roundtrip(tmp_path):
    source = tmp_path / "fusion.sqlite3"
    _db(source)
    result = create_backup(source, tmp_path / "backups", label="test")
    verification = verify_backup(result["backup_path"], result["manifest_path"])
    assert verification["valid"] is True
    assert verification["table_counts"]["world_events_test"] == 2

    target = tmp_path / "restored.sqlite3"
    restored = restore_backup(
        result["backup_path"],
        target,
        manifest_path=result["manifest_path"],
    )
    assert restored["integrity_check"] == "ok"
    with sqlite3.connect(target) as conn:
        assert conn.execute("SELECT COUNT(*) FROM world_events_test").fetchone()[0] == 2


def test_backup_detects_manifest_hash_tampering(tmp_path):
    source = tmp_path / "fusion.sqlite3"
    _db(source)
    result = create_backup(source, tmp_path / "backups")
    manifest_path = result["manifest_path"]
    manifest = json.loads(open(manifest_path, encoding="utf-8").read())
    manifest["sha256"] = "0" * 64
    open(manifest_path, "w", encoding="utf-8").write(json.dumps(manifest))
    try:
        verify_backup(result["backup_path"], manifest_path)
    except ValueError as exc:
        assert "SHA256" in str(exc)
    else:
        raise AssertionError("tampered backup manifest should fail verification")


def test_restore_refuses_overwrite_without_explicit_flag(tmp_path):
    source = tmp_path / "fusion.sqlite3"
    _db(source)
    result = create_backup(source, tmp_path / "backups")
    target = tmp_path / "existing.sqlite3"
    target.write_bytes(b"do-not-overwrite")
    try:
        restore_backup(result["backup_path"], target, manifest_path=result["manifest_path"])
    except FileExistsError:
        pass
    else:
        raise AssertionError("restore should refuse implicit overwrite")
