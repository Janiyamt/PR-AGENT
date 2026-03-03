# PR-Agent v2 — Merge Event Logger

Automatically triggered on every PR merge to `main`.  
Stores structured metadata and an AI-generated Word document for each merge.

---

## How it works

```
PR merged to main
      │
      ▼
GitHub Actions (.github/workflows/merge-agent.yml)
      │
      ├─ [1] event_parser.py   → Is this a PR merge? Extract SHA + PR number
      ├─ [2] github_client.py  → Fetch full PR metadata, files, reviews, issues
      ├─ [3] oci_client.py     → AI analysis via OCI Gen AI (Grok)
      ├─ [4] log_store.py      → Append to merge-log.json (deduplication-safe)
      └─ [5] doc_generator.py  → Rewrite merge-events-report.docx
      │
      ▼
Workflow bot commits updated files back to repo
```

---

## File structure

```
merge_agent/
├── __init__.py
├── main.py           ← pipeline orchestrator
├── event_parser.py   ← detects PR merge vs direct push
├── github_client.py  ← fetches PR/commit/review/issue data
├── oci_client.py     ← OCI Gen AI analysis
├── log_store.py      ← read/write merge-log.json
├── doc_generator.py  ← produces the .docx report
└── logs/
    ├── merge-log.json              ← append-only JSON store (auto-created)
    └── merge-events-report.docx   ← cumulative Word report (auto-created)

.github/workflows/
└── merge-agent.yml   ← triggers on push to main
```

---

## Setup

### 1. Add GitHub Secrets

Go to **Settings → Secrets → Actions** and add:

| Secret | Value |
|---|---|
| `OCI_USER` | Your OCI user OCID |
| `OCI_FINGERPRINT` | API key fingerprint |
| `OCI_TENANCY` | Tenancy OCID |
| `OCI_REGION` | e.g. `us-chicago-1` |
| `OCI_KEY_CONTENT` | Full PEM private key content |
| `OCI_COMPARTMENT_ID` | Compartment OCID |
| `OCI_MODEL_ID` | e.g. `xai.grok-3` |
| `OCI_ENDPOINT` | OCI Gen AI endpoint URL |

> `GITHUB_TOKEN` is automatically provided — you don't add it manually.

### 2. Workflow permissions

In **Settings → Actions → General → Workflow permissions**,  
set to **"Read and write permissions"** so the bot can commit log files.

### 3. Merge any PR to main

The agent fires automatically. Check the **Actions** tab to see it run.  
After it completes, `merge_agent/logs/` will contain the updated log and report.

---

## What gets stored (merge-log.json schema)

```json
{
  "schema_version": "2.0",
  "logged_at": "2026-03-03T10:00:00Z",
  "repo": "owner/repo",
  "merge_commit_sha": "abc123...",
  "merged_at": "2026-03-03 09:58:00",
  "merged_by": "alice",
  "pr_number": 42,
  "pr_title": "Feature: Add login page",
  "pr_author": "bob",
  "source_branch": "feature/login",
  "target_branch": "main",
  "labels": ["enhancement"],
  "additions": 120,
  "deletions": 30,
  "files_changed": ["src/auth.py", "tests/test_auth.py"],
  "commit_count": 4,
  "commit_messages": ["Add login logic", "Fix tests", ...],
  "approvals": ["carol"],
  "changes_requested_by": [],
  "comments": 3,
  "review_comments": 5,
  "linked_issues": [...],
  "file_diffs": [...],
  "ai_analysis": {
    "pr_summary": "...",
    "key_impacts": ["...", "..."],
    "review_notes": "...",
    "before_after": "..."
  }
}
```

---

## v1 compatibility

The original `app.py`, `main.py`, `github_client.py`, `oci_client.py`,  
and `doc_generator.py` at the repo root are **unchanged** — v1 still works.  
v2 lives entirely inside `merge_agent/` and `.github/workflows/merge-agent.yml`.
