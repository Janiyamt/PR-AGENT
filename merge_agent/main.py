# merge_agent/main.py
import sys
import os

# ── Hardcoded config values (same as config.py) ─────────────────────────────
# V2 does not import config.py — values are set here directly as fallbacks.
# GitHub Actions secrets override these via os.environ (set in the workflow).
# To change OCI settings, update these values AND your GitHub Secrets.

os.environ.setdefault("OCI_ENDPOINT",
    "https://inference.generativeai.us-chicago-1.oci.oraclecloud.com")
os.environ.setdefault("OCI_MODEL_ID",
    "xai.grok-4-fast-non-reasoning")
os.environ.setdefault("OCI_COMPARTMENT_ID",
    "ocid1.tenancy.oc1..aaaaaaaahqvb2kliqi35z57qalhpr4dyqbjprclszdcoar2wgc7q6nl36aba")   # <- paste your actual compartment OCID here

# ── Add merge_agent/ folder to path so sibling modules are importable ────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import event_parser
import github_client
import oci_client
import log_store
import doc_generator

# ── Now safe to import agent modules ────────────────────────────────────────
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
        print("Push is not a PR merge - nothing to log. Exiting cleanly.")
        sys.exit(0)

    print(f"PR merge detected: PR #{event['pr_number']} - {event['pr_title']}")

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