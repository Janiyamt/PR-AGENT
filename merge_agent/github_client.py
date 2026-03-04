# merge_agent/github_client.py
# ==============================
# Fetches complete metadata for a single merged PR.
# This is a focused adaptation of the v1 github_client — instead of fetching
# a *list* of PRs on demand, it fetches *one* PR triggered by a real merge event.
#
# DATA RETURNED (the "merge metadata" dict):
#   Everything we know about the merge, structured for both storage (JSON)
#   and document generation (docx).

import requests
import re
from datetime import datetime, timezone


def fetch_merge_metadata(repo: str, pr_number: int, commit_sha: str, token: str) -> dict:
    """
    Fetch all metadata for a merged PR and return one clean dict.

    Args:
        repo:       "owner/repo"
        pr_number:  integer PR number
        commit_sha: the merge commit SHA (from the push event)
        token:      GitHub token

    Returns:
        A flat dict containing everything we want to store and document.
    """
    headers = _build_headers(token)

    # Fetch in parallel-ish order (sequential is fine — Actions has no time pressure)
    pr_detail  = _get(f"repos/{repo}/pulls/{pr_number}", headers)
    files      = _get(f"repos/{repo}/pulls/{pr_number}/files", headers) or []
    reviews    = _get(f"repos/{repo}/pulls/{pr_number}/reviews", headers) or []
    commits    = _get(f"repos/{repo}/pulls/{pr_number}/commits", headers) or []
    issues     = _fetch_linked_issues(repo, pr_detail.get("body", ""), headers)

    return _build_metadata(pr_detail, files, reviews, commits, issues, commit_sha, repo)


# ── Private builders ───────────────────────────────────────────────────────

def _build_metadata(pr, files, reviews, commits, issues, merge_sha, repo) -> dict:
    """
    Transform raw GitHub API responses into a clean, flat metadata dict.
    This is what gets stored in merge-log.json and rendered into the docx.
    """
    approvals          = [r for r in reviews if r.get("state") == "APPROVED"]
    changes_requested  = [r for r in reviews if r.get("state") == "CHANGES_REQUESTED"]
    commit_messages    = [c.get("commit", {}).get("message", "").split("\n")[0] for c in commits]

    return {
        # ── Identity ──────────────────────────────────────────────────────
        "schema_version":   "2.0",                          # bump if fields change
        "logged_at":        _now_iso(),                     # when the agent ran
        "repo":             repo,

        # ── Merge event ───────────────────────────────────────────────────
        "merge_commit_sha": merge_sha,
        "merged_at":        (pr.get("merged_at") or "")[:19].replace("T", " "),
        "merged_by":        pr.get("merged_by", {}).get("login", "N/A"),

        # ── PR basics ─────────────────────────────────────────────────────
        "pr_number":        pr.get("number"),
        "pr_title":         pr.get("title", "No title"),
        "pr_author":        pr.get("user", {}).get("login", "Unknown"),
        "pr_body":          (pr.get("body") or "No description")[:500],
        "pr_url":           pr.get("html_url", ""),
        "source_branch":    pr.get("head", {}).get("ref", "N/A"),   # feature branch
        "target_branch":    pr.get("base", {}).get("ref", "N/A"),   # main
        "labels":           [l.get("name") for l in pr.get("labels", [])],
        "created_at":       (pr.get("created_at") or "")[:10],

        # ── Code changes ──────────────────────────────────────────────────
        "additions":        sum(f.get("additions", 0) for f in files),
        "deletions":        sum(f.get("deletions", 0) for f in files),
        "files_changed":    [f.get("filename") for f in files[:20]],
        "file_diffs": [
            {
                "filename":  f.get("filename"),
                "status":    f.get("status"),
                "additions": f.get("additions", 0),
                "deletions": f.get("deletions", 0),
                "patch":     (f.get("patch") or "")[:1500],   # cap size
            }
            for f in files[:10]
        ],
        "commit_count":     len(commits),
        "commit_messages":  commit_messages[:10],

        # ── Review activity ───────────────────────────────────────────────
        "approvals":              [r.get("user", {}).get("login") for r in approvals],
        "changes_requested_by":   [r.get("user", {}).get("login") for r in changes_requested],
        "comments":               pr.get("comments", 0),
        "review_comments":        pr.get("review_comments", 0),

        # ── Linked issues ─────────────────────────────────────────────────
        "linked_issues":    issues,

        # ── AI analysis placeholder (filled in by oci_client.py) ──────────
        "ai_analysis":      {},
    }


def _fetch_linked_issues(repo: str, body: str, headers: dict) -> list:
    """Find and fetch GitHub issues referenced by 'Fixes #N' / 'Closes #N' in the PR body."""
    pattern      = r'(?:fixes|closes|resolves|fix|close|resolve)\s+#(\d+)'
    issue_nums   = re.findall(pattern, (body or "").lower())
    issues       = []

    for num in issue_nums:
        data = _get(f"repos/{repo}/issues/{num}", headers)
        if data and "number" in data:
            issues.append({
                "number":     data.get("number"),
                "title":      data.get("title", ""),
                "state":      data.get("state", ""),
                "author":     data.get("user", {}).get("login", "Unknown"),
                "created_at": (data.get("created_at") or "")[:10],
                "closed_at":  (data.get("closed_at") or "")[:10] or "Open",
                "labels":     [l.get("name") for l in data.get("labels", [])],
                "body":       (data.get("body") or "")[:300],
                "url":        data.get("html_url", ""),
            })

    return issues


# ── Low-level HTTP helper ──────────────────────────────────────────────────

def _get(path: str, headers: dict):
    """GET from the GitHub API. Returns parsed JSON or None on error."""
    url = f"https://api.github.com/{path}"
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        return resp.json() if resp.status_code == 200 else None
    except requests.RequestException as e:
        print(f"⚠️  GitHub API error ({path}): {e}")
        return None


def _build_headers(token: str) -> dict:
    headers = {
        "Accept":     "application/vnd.github.v3+json",
        "User-Agent": "PR-Agent-Bot-v2",
    }
    if token:
        headers["Authorization"] = f"token {token}"
    return headers


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
