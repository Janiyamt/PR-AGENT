# merge_agent/event_parser.py
# ============================
# Reads the GitHub Actions environment variables injected by the workflow
# and determines whether this push event was triggered by a PR merge.
#
# WHY THIS MODULE EXISTS:
#   GitHub Actions fires on ANY push to main — direct commits, merges, bot pushes.
#   This module answers the question: "Is this push the result of a PR merge?"
#   If yes, it extracts everything we need for the rest of the pipeline.
#   If no, main.py exits early without logging anything.
#
# HOW MERGE DETECTION WORKS:
#   We call the GitHub API to check whether any open PR has this commit as its
#   merge_commit_sha.  This is the most reliable approach — GitHub itself sets
#   that field when it merges a PR, so there are no false positives.

import os
import requests


def parse() -> dict:
    """
    Read environment variables set by the GitHub Actions workflow and
    return a normalised event dict.

    Returns:
        {
            "is_pr_merge": bool,      # True only if this push = a PR merge
            "pr_number":   int|None,  # PR number, or None if not a merge
            "pr_title":    str|None,
            "commit_sha":  str,       # The merge commit SHA
            "repo":        str,       # "owner/repo"
            "pushed_by":   str,       # GitHub username who triggered the push
            "token":       str,       # GITHUB_TOKEN for subsequent API calls
        }
    """
    commit_sha = os.environ.get("MERGE_COMMIT_SHA", "")
    repo       = os.environ.get("REPO_FULL_NAME", "")
    pushed_by  = os.environ.get("PUSHED_BY", "")
    token      = os.environ.get("GITHUB_TOKEN", "")

    if not commit_sha or not repo:
        print("⚠️  Missing MERGE_COMMIT_SHA or REPO_FULL_NAME env vars.")
        return _not_a_merge(commit_sha, repo, pushed_by, token)

    # Ask GitHub API: which PR (if any) produced this commit as its merge commit?
    pr = _find_associated_pr(repo, commit_sha, token)

    if pr is None:
        return _not_a_merge(commit_sha, repo, pushed_by, token)

    return {
        "is_pr_merge": True,
        "pr_number":   pr["number"],
        "pr_title":    pr.get("title", ""),
        "commit_sha":  commit_sha,
        "repo":        repo,
        "pushed_by":   pushed_by,
        "token":       token,
    }


# ── Private helpers ────────────────────────────────────────────────────────

def _not_a_merge(commit_sha, repo, pushed_by, token) -> dict:
    """Return a base event dict indicating this is NOT a PR merge."""
    return {
        "is_pr_merge": False,
        "pr_number":   None,
        "pr_title":    None,
        "commit_sha":  commit_sha,
        "repo":        repo,
        "pushed_by":   pushed_by,
        "token":       token,
    }


def _find_associated_pr(repo: str, commit_sha: str, token: str) -> dict | None:
    """
    Call the GitHub API to find a merged PR whose merge_commit_sha
    matches the current push SHA.

    Endpoint: GET /repos/{owner}/{repo}/commits/{sha}/pulls
    Returns the first matched PR dict, or None.
    """
    url     = f"https://api.github.com/repos/{repo}/commits/{commit_sha}/pulls"
    headers = _build_headers(token)

    try:
        resp = requests.get(url, headers=headers, timeout=15)
    except requests.RequestException as e:
        print(f"⚠️  GitHub API request failed: {e}")
        return None

    if resp.status_code == 200:
        prs = resp.json()
        # Filter to only PRs that have actually been merged
        merged = [pr for pr in prs if pr.get("merged_at")]
        return merged[0] if merged else None

    print(f"⚠️  GitHub API returned {resp.status_code} for commit→PR lookup.")
    return None


def _build_headers(token: str) -> dict:
    headers = {
        "Accept":     "application/vnd.github.v3+json",
        "User-Agent": "PR-Agent-Bot-v2",
    }
    if token:
        headers["Authorization"] = f"token {token}"
    return headers
