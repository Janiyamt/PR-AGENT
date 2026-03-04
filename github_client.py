# github_client.py
# =================
# This module's ONLY job: talk to the GitHub API and return clean data.
# If GitHub changes their API, this is the only file you edit.

import requests
import sys
import config


def _get_headers(token=None):
    """
    Build HTTP headers for GitHub API requests.
    Accepts an optional token — falls back to config.py if not provided.
    This is a private helper (underscore = don't call from outside this file).
    """
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "PR-Agent-Bot"
    }
    active_token = token 
    if active_token:
        # A token lets you make 5000 requests/hour instead of 60
        # Also required for private repos
        headers["Authorization"] = f"token {active_token}"
    return headers


def _handle_response_errors(response, context=""):
    """
    Centralized error handling for GitHub API responses.
    Having this in one place means consistent error messages everywhere.
    """
    if response.status_code == 404:
        print(f" Not found: {context}. Check the repo name.")
        sys.exit(1)
    elif response.status_code == 403:
        print(" Rate limited or access denied. Try adding a GITHUB_TOKEN in config.py")
        sys.exit(1)
    elif response.status_code != 200:
        print(f" GitHub API error {response.status_code}: {response.text}")
        sys.exit(1)


def fetch_pr_list(repo, state="closed", max_count=5, token=None, author=None):
    """
    Fetch a list of pull requests from a GitHub repo.

    Args:
        repo: "owner/repo" string e.g. "vercel/next.js"
        state: "open", "closed", or "all"
        max_count: how many to return (max 100 per GitHub's API)
        token: optional GitHub token (overrides config.py)
        author: optional GitHub username to filter PRs by

    Returns:
        List of raw PR dicts from GitHub
    """
    author_label = f" by {author}" if author else ""
    print(f"Fetching {state} pull requests from {repo}{author_label}...")

    url = f"https://api.github.com/repos/{repo}/pulls"
    params = {
        "state": state,
        "per_page": max_count,
        "sort": "updated",
        "direction": "desc"
    }
    # GitHub API supports filtering by PR creator natively
    if author:
        params["creator"] = author

    response = requests.get(url, headers=_get_headers(token), params=params)
    _handle_response_errors(response, context=f"repo '{repo}'")

    prs = response.json()
    print(f"Found {len(prs)} pull requests")
    return prs


def fetch_pr_details(repo, pr_number, token=None):
    """
    Fetch detailed info for a single PR: files changed, reviews.

    Args:
        repo: "owner/repo" string
        pr_number: integer PR number

    Returns:
        Tuple of (pr_detail dict, files list, reviews list)
    """
    headers = _get_headers(token)
    base_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"

    pr_detail = requests.get(base_url, headers=headers).json()

    files_resp = requests.get(f"{base_url}/files", headers=headers)
    files = files_resp.json() if files_resp.status_code == 200 else []

    reviews_resp = requests.get(f"{base_url}/reviews", headers=headers)
    reviews = reviews_resp.json() if reviews_resp.status_code == 200 else []

    return pr_detail, files, reviews

def fetch_linked_issues(repo, pr_body, pr_number, token=None):
    """
    Extract and fetch issues linked to a PR.
    
    In GitHub, developers link issues by writing in the PR description:
    "Fixes #42", "Closes #123", "Resolves #7"
    We find these using regex, then fetch each issue's details.
    """
    import re
    
    # Regex pattern to find issue references like "Fixes #42", "Closes #123"
    # re.findall returns all matches in the text
    pattern = r'(?:fixes|closes|resolves|fix|close|resolve)\s+#(\d+)'
    issue_numbers = re.findall(pattern, (pr_body or "").lower())
    
    if not issue_numbers:
        return []
    
    issues = []
    for issue_num in issue_numbers:
        url = f"https://api.github.com/repos/{repo}/issues/{issue_num}"
        resp = requests.get(url, headers=_get_headers(token))
        if resp.status_code == 200:
            issue = resp.json()
            issues.append({
                "number": issue.get("number"),
                "title": issue.get("title"),
                "state": issue.get("state"),        # "open" or "closed"
                "author": issue.get("user", {}).get("login", "Unknown"),
                "created_at": issue.get("created_at", "")[:10],
                "closed_at": issue.get("closed_at", "")[:10] if issue.get("closed_at") else "Not closed",
                "labels": [l.get("name") for l in issue.get("labels", [])],
                "body": (issue.get("body") or "No description")[:300],
                "url": issue.get("html_url", "")
            })
    return issues
def extract_pr_info(pr_detail, files, reviews,issues=None):
    """
    Transform raw GitHub API data into a clean, flat dict.

    Why this function exists: GitHub returns huge nested objects.
    This pulls out only what we need, in a simple structure.
    Everything downstream (Grok, doc generator) uses this clean format.

    Args:
        pr_detail: raw PR object from GitHub
        files: list of file objects from GitHub
        reviews: list of review objects from GitHub

    Returns:
        Clean dict with the fields we care about
    """
    approvals = [r for r in reviews if r.get("state") == "APPROVED"]
    changes_requested = [r for r in reviews if r.get("state") == "CHANGES_REQUESTED"]

    return {
        "number": pr_detail.get("number"),
        "title": pr_detail.get("title", "No title"),
        "author": pr_detail.get("user", {}).get("login", "Unknown"),
        "state": pr_detail.get("state", "unknown"),
        "created_at": pr_detail.get("created_at", "")[:10],
        "updated_at": pr_detail.get("updated_at", "")[:10],
        "merged_at": pr_detail.get("merged_at", "")[:10] if pr_detail.get("merged_at") else "Not merged",
        "merged_by": pr_detail.get("merged_by", {}).get("login", "") if pr_detail.get("merged_by") else "",
        "body": (pr_detail.get("body") or "No description")[:500],
        "head_branch": pr_detail.get("head", {}).get("ref", "N/A"),  # source branch (where changes were made)
        "base_branch": pr_detail.get("base", {}).get("ref", "N/A"),  # target branch (where it merges into)
        "labels": [l.get("name") for l in pr_detail.get("labels", [])],
        "files_changed": [f.get("filename") for f in files[:10]],
        "additions": sum(f.get("additions", 0) for f in files),
        "deletions": sum(f.get("deletions", 0) for f in files),
        "linked_issues": issues or [],
        "file_diffs": [
    {
        
        "filename": f.get("filename"),
        "status": f.get("status"),
        "additions": f.get("additions", 0),
        "deletions": f.get("deletions", 0),
        "patch": f.get("patch", "")
    }
    for f in files[:10]
],
        "approvals": [r.get("user", {}).get("login") for r in approvals],
        "changes_requested_by": [r.get("user", {}).get("login") for r in changes_requested],
        "comments": pr_detail.get("comments", 0),
        "review_comments": pr_detail.get("review_comments", 0),
        "commits": pr_detail.get("commits", 0),
    }


def get_all_pr_data(repo, state="closed", max_count=5, token=None, author=None):
    """
    High-level function that combines the three steps above.
    This is what main.py calls — it handles everything and
    returns a ready-to-use list of clean PR dicts.

    Args:
        repo: "owner/repo" string
        state: "open", "closed", or "all"
        max_count: how many PRs to fetch

    Returns:
        List of clean PR info dicts
    """
    raw_prs = fetch_pr_list(repo, state, max_count, token=token, author=author)

    print(f"\nFetching details for each PR...")
    result = []
    for pr in raw_prs:
        pr_number = pr["number"]
        print(f"  → PR #{pr_number}: {pr['title'][:60]}...")
        detail, files, reviews = fetch_pr_details(repo, pr_number, token=token)
        issues = fetch_linked_issues(repo, detail.get("body", ""), pr_number, token=token)
        result.append(extract_pr_info(detail, files, reviews, issues))

    return result