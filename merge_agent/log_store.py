# merge_agent/log_store.py
# ==========================
# Manages merge-log.json — the persistent record of every merge event.
#
# DESIGN DECISIONS:
#   - Single JSON file, append-only.  Easy to read, diff, and audit in git.
#   - Deduplication by merge_commit_sha — if the workflow re-runs for the
#     same commit (e.g. after a rebase), we update the record, not duplicate it.
#   - The file is committed back to the repo by the workflow, so it is
#     version-controlled alongside the code it describes.
#   - schema_version field allows future migrations without breaking old records.
#
# FILE LOCATION:  merge_agent/logs/merge-log.json
# FORMAT:         { "events": [ <metadata dict>, ... ] }

import json
import os
from datetime import datetime, timezone

# Path is relative to the repo root (where the workflow checks out)
_LOG_DIR  = os.path.join(os.path.dirname(__file__), "logs")
_LOG_FILE = os.path.join(_LOG_DIR, "merge-log.json")


def append(metadata: dict) -> None:
    """
    Add (or update) a merge event in merge-log.json.

    If a record with the same merge_commit_sha already exists (re-run),
    it is replaced with the new data.  Otherwise the record is appended.

    Args:
        metadata: the dict produced by github_client + oci_client
    """
    os.makedirs(_LOG_DIR, exist_ok=True)

    events = load_all()

    # Deduplicate by commit SHA
    sha        = metadata.get("merge_commit_sha", "")
    existing   = [e for e in events if e.get("merge_commit_sha") != sha]
    updated    = existing + [metadata]

    _write(updated)
    print(f"  ✅ merge-log.json updated — {len(updated)} total events.")


def load_all() -> list:
    """
    Load all stored merge events from merge-log.json.

    Returns:
        List of metadata dicts, sorted newest-first.
        Returns [] if the file does not exist yet.
    """
    if not os.path.exists(_LOG_FILE):
        return []

    try:
        with open(_LOG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        events = data.get("events", [])
        # Sort newest merge first so the document shows most recent at top
        return sorted(events, key=lambda e: e.get("merged_at", ""), reverse=True)
    except (json.JSONDecodeError, OSError) as e:
        print(f"⚠️  Could not read merge-log.json: {e}")
        return []


def load_latest() -> dict | None:
    """Return the most recently logged event, or None."""
    events = load_all()
    return events[0] if events else None


# ── Private helpers ────────────────────────────────────────────────────────

def _write(events: list) -> None:
    """Write the events list back to disk, wrapped in our top-level structure."""
    payload = {
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_events": len(events),
        "events":       events,
    }
    with open(_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, default=str)
