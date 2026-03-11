# oci_client.py
# ==============
# This module's ONLY job: send data to Grok (via OCI Gen AI) and return AI analysis.
#
# Works in TWO modes:
#   1. Local: reads from ~/.oci/config file (when running on your machine)
#   2. GitHub Actions: reads from environment variables (when running in the cloud)

import json
import os
import config

import oci
from oci.generative_ai_inference import GenerativeAiInferenceClient
from oci.generative_ai_inference.models import (
    ChatDetails,
    GenericChatRequest,
    UserMessage,
    TextContent,
    OnDemandServingMode,
)


def _build_oci_client():
    """
    Create an authenticated OCI Gen AI client.

    Tries environment variables first (GitHub Actions),
    then falls back to ~/.oci/config file (local machine).
    """
    # Check if OCI credentials are available as environment variables
    # This is how GitHub Actions passes them via secrets
    oci_user        = os.environ.get("OCI_USER")
    oci_fingerprint = os.environ.get("OCI_FINGERPRINT")
    oci_tenancy     = os.environ.get("OCI_TENANCY")
    oci_region      = os.environ.get("OCI_REGION")
    oci_key_content = os.environ.get("OCI_KEY_CONTENT")

    if oci_user and oci_fingerprint and oci_tenancy and oci_region and oci_key_content:
        # ── GitHub Actions mode — build config from environment variables ──
        print("   Using OCI credentials from environment variables")

        # Write the private key to a temp file — OCI SDK needs a file path
        key_path = "/tmp/oci_api_key.pem"
        with open(key_path, "w") as f:
            f.write(oci_key_content)
        os.chmod(key_path, 0o600)

        oci_config = {
            "user":        oci_user,
            "fingerprint": oci_fingerprint,
            "tenancy":     oci_tenancy,
            "region":      oci_region,
            "key_file":    key_path,
        }

    else:
        # ── Local mode — read from ~/.oci/config file ──
        print("   Using OCI credentials from config file")
        oci_config = oci.config.from_file(
            file_location=getattr(config, "OCI_CONFIG_FILE", "~/.oci/config"),
            profile_name=getattr(config, "OCI_CONFIG_PROFILE", "DEFAULT")
        )

    oci.config.validate_config(oci_config)

    client = GenerativeAiInferenceClient(
        config=oci_config,
        service_endpoint=config.OCI_ENDPOINT
    )

    return client


def _build_prompt(pr_data_list):
    """Convert PR list into a readable text prompt."""
    pr_text = ""
    for pr in pr_data_list:
        pr_text += f"""
PR #{pr['number']}: {pr['title']}
- Author: {pr['author']}
- State: {pr['state']}
- Created: {pr['created_at']}
- Merged: {pr['merged_at']}
- Merged by: {pr['merged_by'] or 'N/A'}
- Files changed: {', '.join(pr['files_changed'][:5]) or 'N/A'}
- Code changes: +{pr['additions']} lines added / -{pr['deletions']} lines removed
- Approvals from: {', '.join(pr['approvals']) or 'None'}
- Changes requested by: {', '.join(pr['changes_requested_by']) or 'None'}
- Comments: {pr['comments']} general, {pr['review_comments']} review
- Labels: {', '.join(pr['labels']) or 'None'}
- Description: {pr['body'][:200]}
"""

    return f"""You are a technical documentation assistant. Analyze these GitHub Pull Requests and provide:

1. A brief 2-3 sentence summary in points for EACH PR explaining what it does and who was involved
2. An "overall_analysis" in points so its understandable covering key contributors, types of changes, and review culture

PR Data:
{pr_text}

Respond ONLY with valid JSON in this exact structure:
{{
  "pr_summaries": [
    {{"number": 123, "summary": "..."}}
  ],
  "overall_analysis": "..."
}}"""


def _fallback_analysis(pr_data_list):
    """If OCI call fails, return basic analysis so the doc still generates."""
    return {
        "pr_summaries": [
            {"number": pr["number"], "summary": pr["body"][:200]}
            for pr in pr_data_list
        ],
        "overall_analysis": (
            "AI analysis unavailable. Check your OCI credentials."
        )
    }


def analyze_pull_requests(pr_data_list):
    """
    Send PR data to Grok (via OCI Gen AI) and get back AI-generated summaries.
    """
    print("\n Sending PR data to Grok via OCI Gen AI...")

    try:
        client = _build_oci_client()
        prompt = _build_prompt(pr_data_list)

        message = UserMessage(
            content=[TextContent(text=prompt)]
        )

        serving_mode = OnDemandServingMode(model_id=config.OCI_MODEL_ID)

        chat_request = GenericChatRequest(
            messages=[message],
            max_tokens=2000,
            temperature=0.3,
            is_stream=False
        )

        chat_details = ChatDetails(
            compartment_id=config.OCI_COMPARTMENT_ID,
            serving_mode=serving_mode,
            chat_request=chat_request
        )

        response = client.chat(chat_details)
        choices = response.data.chat_response.choices
        raw_text = choices[0].message.content[0].text

        print(" OCI Gen AI response received!")

    except oci.exceptions.ConfigFileNotFound:
        print("⚠️  OCI config file not found.")
        return _fallback_analysis(pr_data_list)
    except oci.exceptions.InvalidConfig as e:
        print(f"⚠️  OCI config is invalid: {e}")
        return _fallback_analysis(pr_data_list)
    except Exception as e:
        print(f"⚠️  OCI Gen AI call failed: {e}")
        return _fallback_analysis(pr_data_list)

    clean_text = raw_text.strip().removeprefix("```json").removesuffix("```").strip()

    try:
        analysis = json.loads(clean_text)
        print(" Analysis parsed successfully!")
        return analysis
    except json.JSONDecodeError:
        print("  Could not parse response as JSON, using raw text")
        return {"pr_summaries": [], "overall_analysis": raw_text}