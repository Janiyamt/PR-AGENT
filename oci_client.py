# oci_client.py
# ==============
# This module's ONLY job: send data to Grok (via OCI Gen AI) and return AI analysis.

import json
import config

# oci.config           → reads and validates your ~/.oci/config file
# oci.generative_ai_inference → the client that talks to Gen AI service
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
    Create an authenticated OCI Gen AI client using ~/.oci/config.

    oci.config.from_file() reads your config file and returns a dict.
    We pass that dict to the client — it handles request signing from there.
    """
    # Load config from file — raises an error with a helpful message if missing
    oci_config = oci.config.from_file(
        file_location=config.OCI_CONFIG_FILE,
        profile_name=config.OCI_CONFIG_PROFILE
    )

    # Validate the config has all required fields
    oci.config.validate_config(oci_config)

    # Create the Gen AI inference client
    # service_endpoint tells it which OCI region's Gen AI to use
    client = GenerativeAiInferenceClient(
        config=oci_config,
        service_endpoint=config.OCI_ENDPOINT
    )

    return client


def _build_prompt(pr_data_list):
    """
    Convert our list of PR dicts into a readable text prompt.
    Kept separate so you can tweak the prompt without touching API logic.
    """
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
    """
    If the OCI API call fails, return basic analysis so the doc still generates.
    Always have a fallback — never let an LLM failure crash the whole program.
    """
    return {
        "pr_summaries": [
            {"number": pr["number"], "summary": pr["body"][:200]}
            for pr in pr_data_list
        ],
        "overall_analysis": (
            "AI analysis unavailable. Check your OCI config:\n"
            "  - Is ~/.oci/config present with [DEFAULT] profile?\n"
            "  - Is OCI_COMPARTMENT_ID set correctly in config.py?\n"
            "  - Is OCI_MODEL_ID a valid model in your region?"
        )
    }


def analyze_pull_requests(pr_data_list):
    """
    Send PR data to Grok (via OCI Gen AI) and get back AI-generated summaries.

    OCI Gen AI uses a "chat" interface:
      - You create a ChatDetails object with your message
      - The client sends it to OCI and returns a response object
      - You pull the text out of response.data.chat_response.choices[0]

    Args:
        pr_data_list: list of clean PR dicts (from github_client.py)

    Returns:
        Dict with keys:
            - "pr_summaries": list of {number, summary} dicts
            - "overall_analysis": string with team/repo insights
    """
    print("\n Sending PR data to Grok via OCI Gen AI...")

    try:
        # Step 1: Build authenticated client
        client = _build_oci_client()

        # Step 2: Build the prompt
        prompt = _build_prompt(pr_data_list)

        # Step 3: Wrap prompt in OCI's message format
        # OCI uses a structured message object, not a plain string
        message = UserMessage(
            content=[TextContent(text=prompt)]
        )

        # Step 4: Configure which model to use and how
        # OnDemandServingMode means "use the model on demand" (vs dedicated endpoint)
        serving_mode = OnDemandServingMode(model_id=config.OCI_MODEL_ID)

        # Step 5: Build the full chat request
        chat_request = GenericChatRequest(
            messages=[message],
            max_tokens=2000,
            temperature=0.3,       # Lower = more factual, less creative
            is_stream=False        # Get full response at once (not token by token)
        )

        # Step 6: Build the outer ChatDetails wrapper
        chat_details = ChatDetails(
            compartment_id=config.OCI_COMPARTMENT_ID,
            serving_mode=serving_mode,
            chat_request=chat_request
        )

        # Step 7: Make the API call
        response = client.chat(chat_details)

        # Step 8: Extract the text from the nested response structure
        # response.data.chat_response.choices[0].message.content[0].text
        choices = response.data.chat_response.choices
        raw_text = choices[0].message.content[0].text

        print(" OCI Gen AI response received!")

    except oci.exceptions.ConfigFileNotFound:
        print("⚠️  OCI config file not found. Make sure ~/.oci/config exists.")
        return _fallback_analysis(pr_data_list)
    except oci.exceptions.InvalidConfig as e:
        print(f"⚠️  OCI config is invalid: {e}")
        return _fallback_analysis(pr_data_list)
    except Exception as e:
        print(f"⚠️  OCI Gen AI call failed: {e}")
        return _fallback_analysis(pr_data_list)

    # Step 9: Parse the JSON that Grok returned
    # Strip any markdown code fences Grok might wrap around the JSON
    clean_text = raw_text.strip().removeprefix("```json").removesuffix("```").strip()

    try:
        analysis = json.loads(clean_text)
        print(" Analysis parsed successfully!")
        return analysis
    except json.JSONDecodeError:
        print("  Could not parse response as JSON, using raw text")
        return {"pr_summaries": [], "overall_analysis": raw_text}