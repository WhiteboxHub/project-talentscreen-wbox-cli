"""One-shot probe: discover the exact JSON key the WBL backend uses for the
"Source" column visible in the user dashboard (values like ``Linkedin``,
``Jobright``, ``Trueup.Io``, ``Hiring.Cafe`` ...).

JobCLI's discoverer currently ignores this field. Before we add a `source`
column to the local schema and an ``apply --sources`` filter, we need to lock
in the exact key name. This script:

  1. Instantiates SyncClient (uses credentials saved in ~/.jobcli/jobcli.db)
  2. Calls GET /positions/cli_window?page_size=3
  3. Prints every key present on the first row
  4. Prints the value of the most likely candidates so a human can eyeball
  5. Falls back to /positions/paginated if cli_window 422s

Read-only. No DB writes. Run once with:

    python scripts/probe_source_key.py
"""

from __future__ import annotations

import json
import sys
from typing import Any, Iterable

from jobcli.sync.client import SyncClient


CANDIDATE_KEYS = (
    "source",
    "job_source",
    "listing_source",
    "posting_source",
    "provider",
    "origin",
    "channel",
)


def _pp(rows: Iterable[dict[str, Any]], label: str) -> None:
    rows = list(rows)
    if not rows:
        print(f"\n[{label}] returned no rows.")
        return
    print(f"\n[{label}] first-row keys ({len(rows)} rows total):")
    print("  " + ", ".join(sorted(rows[0].keys())))
    print(f"\n[{label}] candidate-key values across first {min(len(rows), 5)} rows:")
    for key in CANDIDATE_KEYS:
        if key in rows[0]:
            values = [rows[i].get(key) for i in range(min(len(rows), 5))]
            print(f"  {key!r:>20} -> {values}")
    print(f"\n[{label}] full first row (JSON):")
    print(json.dumps(rows[0], indent=2, default=str))


def main() -> int:
    client = SyncClient()
    found_any = False

    print("Probing /positions/cli_window ...")
    try:
        payload = client.fetch_cli_window_listings(page_size=5, status="open")
        data = payload.get("data") or []
        _pp(data, "cli_window")
        found_any = bool(data)
    except Exception as exc:
        print(f"  cli_window failed: {exc}")

    if not found_any:
        return 1

    print(
        "\nDone. Pick the key whose values look like 'Linkedin', 'Jobright',\n"
        "'Trueup.Io', 'Hiring.Cafe', etc. That is the key to hard-wire as\n"
        "`_SOURCE_API_KEY` in jobcli/core/wbox_discoverer.py."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
