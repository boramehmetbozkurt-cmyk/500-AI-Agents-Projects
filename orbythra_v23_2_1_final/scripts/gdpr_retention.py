from __future__ import annotations

import argparse
import json
import time

from app.store import STORE


def main() -> int:
    parser = argparse.ArgumentParser(description="Purge expired ORBYTHRA GDPR privacy records for one workspace.")
    parser.add_argument("--workspace", required=True)
    args = parser.parse_args()
    now = int(time.time())
    purged = STORE.purge_expired_privacy_records(workspace_id=args.workspace, now=now)
    print(json.dumps({"workspace_id": args.workspace, "purged_records": purged, "purged_at": now}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
