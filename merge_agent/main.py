# merge_agent/main.py
# ====================
# Entry point for the merge agent pipeline.
# Called by GitHub Actions after every push to main.
#
# Pipeline:
#   1. event_parser   → detect if this push is a real PR merge, extract context
#   2. github_client  → fetch full PR + commit metadata from GitHub API
#   3. oci_client     → AI analysis of what changed (reuses v1 logic)
#   4. log_store      → append event to merge-log.json
#   5. doc_generator  → write / update the running merge-events .docx report

import sys
import os

# Ensure the package root is on the path when run directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from merge_agent import event_parser, github_client, oci_client, log_store, doc_generator


def main():
    print()
    print("=" * 52)
    print("     PR Merge Agent  v2")
    print("=" * 52)

    # ── Step 1: Parse the GitHub push event ─────────────────────────────────
    print("\n[1/5] Parsing push event...")
    event = event_parser.parse()

    if not event["is_pr_merge"]:
        # This push was a direct commit to main, not a PR merge — skip silently.
        # We only want to log PR merges, not every push.
        print("⏭  Push is not a PR merge — nothing to log. Exiting cleanly.")
        sys.exit(0)

    print(f"✅ PR merge detected: PR #{event['pr_number']} — {event['pr_title']}")

    # ── Step 2: Fetch full metadata from GitHub API ──────────────────────────
    print("\n[2/5] Fetching PR metadata from GitHub API...")
    metadata = github_client.fetch_merge_metadata(
        repo=event["repo"],
        pr_number=event["pr_number"],
        commit_sha=event["commit_sha"],
        token=event["token"],
    )

    # ── Step 3: AI analysis via OCI Gen AI ──────────────────────────────────
    print("\n[3/5] Running AI analysis...")
    analysis = oci_client.analyze_merge_event(metadata)
    metadata["ai_analysis"] = analysis   # attach to metadata before storing

    # ── Step 4: Append to merge-log.json ────────────────────────────────────
    print("\n[4/5] Storing metadata in merge-log.json...")
    log_store.append(metadata)

    # ── Step 5: Regenerate the running .docx report ──────────────────────────
    print("\n[5/5] Updating merge events Word document...")
    all_events = log_store.load_all()
    doc_generator.generate(all_events, repo=event["repo"])

    print("\n🎉 Merge agent completed successfully.")
    print(f"   PR #{event['pr_number']} logged | {len(all_events)} total merges on record\n")


if __name__ == "__main__":
    main()
