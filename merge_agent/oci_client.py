# merge_agent/oci_client.py
# ==========================
# AI analysis for a single merge event, using OCI Gen AI (Grok).
# Adapted from v1 — the difference is that v1 analysed a *batch* of PRs;
# this module analyses *one* merge event with richer context (diffs, commits).
#
# In GitHub Actions, OCI credentials arrive as environment variables
# (set from GitHub Secrets in the workflow).  We build the OCI config
# dict from env vars instead of reading ~/.oci/config.

import os
import json


def analyze_merge_event(metadata: dict) -> dict:
    """
    Send merge metadata to OCI Gen AI and return structured analysis.

    Args:
        metadata: the clean dict produced by github_client.fetch_merge_metadata()

    Returns:
        {
            "pr_summary":      "2-3 sentence summary of what this PR did",
            "key_impacts":     ["functional change 1", "risk note", ...],
            "review_notes":    "Notes on the review process",
            "before_after":    "What the code looked like before vs after",
        }
    """
    print("  Sending to OCI Gen AI for analysis...")
    try:
        client   = _build_client()
        prompt   = _build_prompt(metadata)
        response = _call_api(client, prompt)
        result   = _parse_response(response)
        print("  ✅ AI analysis complete.")
        return result
    except Exception as e:
        print(f"  ⚠️  OCI Gen AI failed — using fallback: {e}")
        return _fallback(metadata)


# ── Private helpers ────────────────────────────────────────────────────────

# merge_agent/oci_client.py
# replace the _build_client() function with this:

def _build_client():
    import oci
    from oci.generative_ai_inference import GenerativeAiInferenceClient
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import config

    key_content = os.environ.get("OCI_KEY_CONTENT", "").strip()

    if key_content:
        # Running in GitHub Actions — build config from env vars
        oci_config = {
            "user":        os.environ["OCI_USER"],
            "fingerprint": os.environ["OCI_FINGERPRINT"],
            "tenancy":     os.environ["OCI_TENANCY"],
            "region":      os.environ["OCI_REGION"],
            "key_content": key_content,
        }
    else:
        # Running locally — use ~/.oci/config file (same as V1)
        oci_config = oci.config.from_file(
            file_location=config.OCI_CONFIG_FILE,
            profile_name=config.OCI_CONFIG_PROFILE
        )

    oci.config.validate_config(oci_config)
    return GenerativeAiInferenceClient(
        config=oci_config,
        service_endpoint=config.OCI_ENDPOINT
    )


def _build_prompt(m: dict) -> str:
    """Format the merge metadata into a concise prompt for Grok."""
    files_summary = ", ".join(m.get("files_changed", [])[:8]) or "N/A"
    commits_summary = "\n".join(f"  - {msg}" for msg in m.get("commit_messages", [])[:5]) or "  (none)"

    # Only include diffs for the first few files to keep the prompt manageable
    diff_text = ""
    for d in m.get("file_diffs", [])[:4]:
        patch = (d.get("patch") or "")[:600]
        if patch:
            diff_text += f"\nFILE: {d['filename']} (+{d['additions']}/-{d['deletions']})\n{patch}\n"

    return f"""You are a senior engineering lead reviewing a merged Pull Request.
Provide a concise, accurate analysis for a non-technical stakeholder document.

REPOSITORY: {m.get('repo')}
PR #{m.get('pr_number')}: {m.get('pr_title')}
Author:      {m.get('pr_author')}
Merged by:   {m.get('merged_by')}
Merged at:   {m.get('merged_at')}
Branch:      {m.get('source_branch')} → {m.get('target_branch')}
Labels:      {', '.join(m.get('labels', [])) or 'None'}

Commits ({m.get('commit_count', 0)} total):
{commits_summary}

Files changed ({len(m.get('files_changed', []))} files): {files_summary}
Code delta: +{m.get('additions', 0)} additions / -{m.get('deletions', 0)} deletions

Approvals from: {', '.join(m.get('approvals', [])) or 'None'}
Changes requested by: {', '.join(m.get('changes_requested_by', [])) or 'None'}

PR Description:
{m.get('pr_body', 'No description')[:400]}

Code diffs (sample):
{diff_text or '(no diffs available)'}

Respond ONLY with valid JSON — no markdown fences, no preamble:
{{
  "pr_summary":    "2-3 sentences: what did this PR do and why? mention key files/components affected.",
  "key_impacts":   ["functional impact", "potential risk or edge case", "performance or security note"],
  "review_notes":  "1-2 sentences on the review process — who approved, any concerns raised?",
  "before_after":  "1-2 sentences: what the relevant code/behaviour was before vs after this merge."
}}"""


def _call_api(client, prompt: str) -> str:
    from oci.generative_ai_inference.models import (
        ChatDetails, GenericChatRequest,
        UserMessage, TextContent, OnDemandServingMode,
    )
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import config

    # Use env var if set, otherwise fall back to config.py
    model_id       = os.environ.get("OCI_MODEL_ID")       or config.OCI_MODEL_ID
    compartment_id = os.environ.get("OCI_COMPARTMENT_ID") or config.OCI_COMPARTMENT_ID
    endpoint       = os.environ.get("OCI_ENDPOINT")       or config.OCI_ENDPOINT

    message      = UserMessage(content=[TextContent(text=prompt)])
    serving_mode = OnDemandServingMode(model_id=model_id)
    chat_request = GenericChatRequest(
        messages=[message], max_tokens=800, temperature=0.3, is_stream=False
    )
    chat_details = ChatDetails(
        compartment_id=compartment_id,
        serving_mode=serving_mode,
        chat_request=chat_request,
    )
    response = client.chat(chat_details)
    return response.data.chat_response.choices[0].message.content[0].text


def _parse_response(raw: str) -> dict:
    """Strip markdown fences and parse JSON."""
    clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(clean)


def _fallback(metadata: dict) -> dict:
    """Safe fallback when OCI is unavailable — uses raw metadata."""
    return {
        "pr_summary":   (metadata.get("pr_body") or "No description.")[:300],
        "key_impacts":  [f"Changed {len(metadata.get('files_changed', []))} file(s)"],
        "review_notes": f"Approved by: {', '.join(metadata.get('approvals', [])) or 'No approvals recorded.'}",
        "before_after": "AI analysis unavailable — check OCI credentials in GitHub Secrets.",
    }
