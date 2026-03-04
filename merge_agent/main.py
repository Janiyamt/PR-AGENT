# merge_agent/main.py
import sys
import os

# Add repo root to path BEFORE any other imports
# This ensures config.py is found whether running locally or in GitHub Actions
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# Now import modules individually (NOT as a package)
# Importing as "from merge_agent import ..." causes oci_client.py to load
# before our path fix is in place — importing directly avoids this
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import event_parser
import github_client
import oci_client
import log_store
import doc_generator


def main():
    print()
    print("=" * 52)
    print("     PR Merge Agent  v2")
    print("=" * 52)

    print("\n[1/5] Parsing push event...")
    event = event_parser.parse()

    if not event["is_pr_merge"]:
        print("Push is not a PR merge — nothing to log. Exiting cleanly.")
        sys.exit(0)

    print(f"PR merge detected: PR #{event['pr_number']} — {event['pr_title']}")

    print("\n[2/5] Fetching PR metadata from GitHub API...")
    metadata = github_client.fetch_merge_metadata(
        repo=event["repo"],
        pr_number=event["pr_number"],
        commit_sha=event["commit_sha"],
        token=event["token"],
    )

    print("\n[3/5] Running AI analysis...")
    analysis = oci_client.analyze_merge_event(metadata)
    metadata["ai_analysis"] = analysis

    print("\n[4/5] Storing metadata in merge-log.json...")
    log_store.append(metadata)

    print("\n[5/5] Updating merge events Word document...")
    all_events = log_store.load_all()
    doc_generator.generate(all_events, repo=event["repo"])

    print("\nMerge agent completed successfully.")
    print(f"   PR #{event['pr_number']} logged | {len(all_events)} total merges on record\n")


if __name__ == "__main__":
    main()