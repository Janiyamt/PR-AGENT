# main.py
# ========
# Asks the user the minimum needed to run, then wires all modules together.
#
# Only repo name is required — everything else has a default so
# the user can just hit Enter and the agent runs immediately.

import os
import sys
import config
import github_client
import oci_client
import doc_generator


def get_user_inputs():
    print()
    print("=" * 42)
    print("     PR Agent")
    print("=" * 42)
    print()

    # Only truly required input — no default makes sense here
    repo = input("  GitHub repo (owner/repo): ").strip()
    if not repo:
        print("❌ Repo is required. Example: shreyaa/my-project")
        sys.exit(1)

    # Everything below: just press Enter to use the shown default
    token = input("  GitHub token (Enter to skip): ").strip() or None
    author = input("  Filter by author (Enter for all PRs): ").strip() or None
    state = input("  PR state — open/closed/all (Enter for 'closed'): ").strip() or "closed"

    count_raw = input("  How many PRs (Enter for 5): ").strip()
    max_prs = int(count_raw) if count_raw.isdigit() else 5

    print()
    return repo, token, author, state, max_prs


def main():
    repo, token, author, state, max_prs = get_user_inputs()

    print(f" Fetching {max_prs} {state} PRs from {repo}")
    if author:
        print(f"   Filtered to: {author}")
    print()

    # Step 1: GitHub
    pr_data = github_client.get_all_pr_data(
        repo=repo, state=state, max_count=max_prs, token=token, author=author
    )

    if not pr_data:
        print("No pull requests found. Try a different state or remove the author filter.")
        sys.exit(0)

    # Step 2: OCI Gen AI
    analysis = oci_client.analyze_pull_requests(pr_data)

    # Step 3: Word doc
    output_path = os.path.join(os.path.dirname(__file__), config.OUTPUT_FILE)
    doc_generator.generate(pr_data, analysis, repo, output_path)

    print(f"\n Done! Open '{config.OUTPUT_FILE}' to see your report.")


if __name__ == "__main__":
    main()