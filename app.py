# app.py
# =======
# Streamlit UI for the PR Documentation Agent.
# Replaces main.py — run this instead with: streamlit run app.py
#
# HOW STREAMLIT WORKS:
# - Every time the user interacts (clicks button, types), the whole script re-runs
# - st.session_state is a dict that persists between re-runs — we use it to
#   store fetched PR data and chat history so they don't disappear on re-run'''
import streamlit as st
import config
import github_client
import oci_client

# ── Page config — must be the very first Streamlit call ──
# This comment is added to check if the v2 bot is working
st.set_page_config(
    page_title="PR Agent",
    page_icon="🤖",
    layout="wide"
)


# ─────────────────────────────────────────────
# SESSION STATE SETUP
# st.session_state persists across re-runs.
# We initialize keys here so they always exist.
# ─────────────────────────────────────────────

if "pr_data" not in st.session_state:
    st.session_state.pr_data = None        # List of PR dicts once fetched

if "analysis" not in st.session_state:
    st.session_state.analysis = None       # AI analysis dict

if "repo" not in st.session_state:
    st.session_state.repo = ""             # Repo name used for current data

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []     # List of {"role": "user"/"assistant", "content": "..."}


# ─────────────────────────────────────────────
# HELPER — Q&A using OCI Gen AI
# THIS CHANGES ARE MADE TO CHECK THE OCI SERVICES in detail using a bot
# ─────────────────────────────────────────────

def answer_question(question, pr_data, analysis):
    """
    Send the user's question + all PR data to Grok and get an answer.

    We include the full PR data as context in every message so Grok
    can answer questions about any PR without needing memory.
    """
    # Format PR data as readable text for the prompt
    pr_context = ""
    for pr in pr_data:
        pr_context += f"""
PR #{pr['number']}: {pr['title']}
- Author: {pr['author']}
- State: {pr['state']}
- Created: {pr['created_at']} | Merged: {pr['merged_at']}
- Merged by: {pr.get('merged_by') or 'N/A'}
- Code changes: +{pr.get('additions', 0)} additions / -{pr.get('deletions', 0)} deletions
- Files changed: {', '.join(pr.get('files_changed', [])[:5]) or 'N/A'}
- Approvals: {', '.join(pr.get('approvals', [])) or 'None'}
- Changes requested by: {', '.join(pr.get('changes_requested_by', [])) or 'None'}
- Comments: {pr.get('comments', 0)} | Review comments: {pr.get('review_comments', 0)}
- Labels: {', '.join(pr.get('labels', [])) or 'None'}
- Description: {pr.get('body', '')[:300]}
"""

    overall = analysis.get("overall_analysis", "") if analysis else ""

    prompt = f"""You are an assistant helping analyze GitHub Pull Requests.

Here is the PR data:
{pr_context}

Overall analysis:
{overall}

Answer this question concisely and clearly:
{question}
"""

    import json, requests

    try:
        import oci
        from oci.generative_ai_inference import GenerativeAiInferenceClient
        from oci.generative_ai_inference.models import (
            ChatDetails, GenericChatRequest, UserMessage,
            TextContent, OnDemandServingMode
        )

        oci_config = oci.config.from_file(config.OCI_CONFIG_FILE, config.OCI_CONFIG_PROFILE)
        client = GenerativeAiInferenceClient(config=oci_config, service_endpoint=config.OCI_ENDPOINT)

        message = UserMessage(content=[TextContent(text=prompt)])
        serving_mode = OnDemandServingMode(model_id=config.OCI_MODEL_ID)
        chat_request = GenericChatRequest(messages=[message], max_tokens=1000, temperature=0.3, is_stream=False)
        chat_details = ChatDetails(compartment_id=config.OCI_COMPARTMENT_ID, serving_mode=serving_mode, chat_request=chat_request)

        response = client.chat(chat_details)
        return response.data.chat_response.choices[0].message.content[0].text

    except Exception as e:
        return f"⚠️ Could not get answer: {e}"


# ─────────────────────────────────────────────
# UI — HEADER
# ─────────────────────────────────────────────

st.title("PR Agent")
st.caption("Fetch, analyze, and query GitHub Pull Requests using AI")
st.divider()


# ─────────────────────────────────────────────
# UI — SIDEBAR (inputs)
# Sidebar keeps inputs out of the way once report is shown
# ─────────────────────────────────────────────

with st.sidebar:
    st.header("⚙️ Settings")
    st.caption("Fill in the details and click Generate")

    repo  = st.text_input("GitHub Repo (owner/repo)")
    token = st.text_input("GitHub Token (optional)", type="password", placeholder="For private repos")
    author = st.text_input("Filter by Author (optional)")

    col1, col2 = st.columns(2)
    with col1:
        state = st.selectbox("PR State", ["closed", "open", "all"])
    with col2:
        count = st.number_input("Count", min_value=1, max_value=50, value=5)

    generate_btn = st.button("Generate Report", use_container_width=True, type="primary")

    # Show a reset button once data is loaded
    if st.session_state.pr_data:
        if st.button("Reset", use_container_width=True):
            st.session_state.pr_data = None
            st.session_state.analysis = None
            st.session_state.chat_history = []
            st.session_state.repo = ""
            st.rerun()


# ─────────────────────────────────────────────
# FETCH + ANALYZE — runs when button is clicked
# ─────────────────────────────────────────────

if generate_btn:
    if not repo:
        st.error("Please enter a GitHub repo name.")
    else:
        # Step 1: Fetch PRs
        with st.spinner(f"Fetching PRs from {repo}..."):
            try:
                pr_data = github_client.get_all_pr_data(
                    repo=repo,
                    state=state,
                    max_count=count,
                    token=token or None,
                    author=author or None
                )
            except SystemExit:
                st.error("Could not fetch PRs. Check the repo name and try again.")
                st.stop()

        if not pr_data:
            st.warning("No pull requests found. Try changing the state or removing the author filter.")
            st.stop()

        # Step 2: AI Analysis
        with st.spinner("Analyzing with Grok via OCI Gen AI..."):
            analysis = oci_client.analyze_pull_requests(pr_data)

        # Store in session state so it persists across re-runs
        st.session_state.pr_data = pr_data
        st.session_state.analysis = analysis
        st.session_state.repo = repo
        st.session_state.chat_history = []   # Reset chat for new repo
        st.rerun()   # Re-run to show the report


# ─────────────────────────────────────────────
# REPORT DISPLAY — shown once data is fetched
# ─────────────────────────────────────────────

if st.session_state.pr_data:
    pr_data  = st.session_state.pr_data
    analysis = st.session_state.analysis
    repo     = st.session_state.repo

    # ── Overview stats ──
    merged       = sum(1 for pr in pr_data if pr.get("merged_at") != "Not merged")
    contributors = len(set(pr["author"] for pr in pr_data))
    additions    = sum(pr.get("additions", 0) for pr in pr_data)
    deletions    = sum(pr.get("deletions", 0) for pr in pr_data)

    st.subheader(f"📁 {repo}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total PRs",     len(pr_data))
    c2.metric("Merged",        merged)
    c3.metric("Contributors",  contributors)
    c4.metric("Lines Changed", f"+{additions}/-{deletions}")

    st.divider()

    # ── AI Overall Analysis ──
    st.subheader("AI Analysis")
    st.info(analysis.get("overall_analysis", "No analysis available."))

    st.divider()

    # ── Individual PR cards ──
    st.subheader("Pull Request Details")

    # Build AI summary lookup
    summary_map = {
        str(s["number"]): s["summary"]
        for s in analysis.get("pr_summaries", [])
    }

    for pr in pr_data:
        # Colored status badge
        state_color = {"closed": "🔴", "open": "🟢"}.get(pr.get("state", ""), "⚪")
        merged_label = f"✅ Merged {pr['merged_at']}" if pr.get("merged_at") != "Not merged" else f"{state_color} {pr.get('state', '').upper()}"

        with st.expander(f"PR #{pr['number']} — {pr['title']}", expanded=False):

            # AI summary at the top
            ai_summary = summary_map.get(str(pr["number"]))
            if ai_summary:
                st.success(f"💡{ai_summary}")

            # Two columns: left = key info, right = people + files
            left, right = st.columns(2)

            with left:
                st.markdown("**Details**")
                st.markdown(f"- **Author:** {pr.get('author', 'N/A')}")
                st.markdown(f"- **Status:** {merged_label}")
                st.markdown(f"- **Merged by:** {pr.get('merged_by') or 'N/A'}")
                st.markdown(f"- **Created:** {pr.get('created_at', 'N/A')}")
                st.markdown(f"- **Commits:** {pr.get('commits', 0)}")
                st.markdown(f"- **Code:** +{pr.get('additions', 0)} / -{pr.get('deletions', 0)}")
                st.markdown(f"- **Labels:** {', '.join(pr.get('labels', [])) or 'None'}")

            with right:
                st.markdown("**Review**")
                st.markdown(f"- **Approvals:** {', '.join(pr.get('approvals', [])) or 'None'}")
                st.markdown(f"- **Changes requested:** {', '.join(pr.get('changes_requested_by', [])) or 'None'}")
                st.markdown(f"- **Comments:** {pr.get('comments', 0)} general, {pr.get('review_comments', 0)} review")
                st.markdown("**Files Changed**")
                files = pr.get("files_changed", [])[:5]
                for f in files:
                    st.code(f, language=None)

                # Code diff section
                file_diffs = pr.get("file_diffs", [])
                if file_diffs:
                    st.markdown("**Code Changes**")
                    st.caption("Lines with + were added, lines with - were removed")
                    for diff in file_diffs:
                        status_icon = {"added": "🟢 Added", "modified": "🟡 Modified", "removed": "🔴 Removed", "renamed": "🔵 Renamed"}.get(diff.get("status"), "⚪ Changed")
                        with st.expander(f"{status_icon}  {diff.get('filename')}  (+{diff.get('additions', 0)} / -{diff.get('deletions', 0)})", expanded=False):
                            if diff.get("patch"):
                                st.code(diff.get("patch"), language="diff")
                            else:
                                st.caption("No diff available — binary file or too large")

            # PR description
            if pr.get("body") and pr["body"] != "No description":
                st.markdown("**Description**")
                st.caption(pr["body"][:400])

    st.divider()

    # ─────────────────────────────────────────────
    # Q&A SECTION
    # ─────────────────────────────────────────────

    st.subheader("💬Ask Questions About These PRs")
    st.caption("Ask anything about the PRs — who contributed most, what changed, review patterns, etc.")

    # Show chat history
    # Each message is {"role": "user"/"assistant", "content": "..."}
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Chat input box — appears at the bottom
    question = st.chat_input("e.g. Who reviewed the most PRs? Which PR changed the most files?")

    if question:
        # Show user message immediately
        with st.chat_message("user"):
            st.markdown(question)
        st.session_state.chat_history.append({"role": "user", "content": question})

        # Get answer from Grok
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                answer = answer_question(question, pr_data, analysis)
            st.markdown(answer)
        st.session_state.chat_history.append({"role": "assistant", "content": answer})

else:
    # Nothing fetched yet — show instructions
    st.info("👈Enter a GitHub repo in the sidebar and click **Generate Report** to get started.")
   
