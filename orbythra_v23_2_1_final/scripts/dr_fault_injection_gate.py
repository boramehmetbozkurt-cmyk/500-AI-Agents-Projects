from __future__ import annotations
import json,sqlite3,tempfile
from pathlib import Path
from scripts.restore_drill import sqlite_backup,integrity,existing_tables
def run():
 with tempfile.TemporaryDirectory(prefix="orbythra-dr2-") as d:
  root=Path(d);src=root/"source.db";backup=root/"backup.db";corrupt=root/"corrupt.db";restored=root/"restored.db"
  with sqlite3.connect(src) as c:c.execute("CREATE TABLE critical(id INTEGER PRIMARY KEY,v TEXT)");c.execute("INSERT INTO critical(v) VALUES ('proof')")
  sqlite_backup(src,backup);corrupt.write_bytes(b"corrupted-not-a-database")
  corruption_detected=False
  try:integrity(corrupt)
  except sqlite3.DatabaseError:corruption_detected=True
  sqlite_backup(backup,restored)
  with sqlite3.connect(restored) as c:value=c.execute("SELECT v FROM critical").fetchone()[0]
  passed=corruption_detected and integrity(restored)=="ok" and value=="proof" and existing_tables(src)==existing_tables(restored)
  return {"drill":"corruption_detection_and_clean_restore","passed":passed,"corruption_detected":corruption_detected,"restored_integrity":integrity(restored),"data_verified":value=="proof","boundary":"Local SQLite DR fault-injection; production managed-database RPO/RTO remains deployment evidence."}
if __name__=="__main__":
 r=run();print(json.dumps(r,indent=2));raise SystemExit(0 if r["passed"] else 1)
