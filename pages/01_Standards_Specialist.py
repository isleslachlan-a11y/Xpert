"""
Meridian -- Standards Specialist page.
Primary product page: RAG-powered chat interface backed by the LlamaIndex ReActAgent.

Architecture:
  - Agent is built once on first load and cached in st.session_state.agent.
  - Chat history lives in st.session_state.messages as [{"role", "content"}] dicts.
  - Sidebar project context is prepended to every agent query as a plain-text
    prefix; only the clean user prompt is stored in message history.
  - Suggested questions are rendered when the conversation is empty. Clicking
    one writes the text into st.session_state.pending_prompt and triggers
    st.rerun() so it flows through the normal chat-input path.
"""

from __future__ import annotations

import os

import streamlit as st

st.set_page_config(
    page_title="Standards Specialist -- Meridian",
    page_icon="§",
    layout="wide",
)

# ── Suggested questions ───────────────────────────────────────────────────────

_SUGGESTED_QUESTIONS: list[str] = [
    "What ventilation rate does AS 1668.2 require for an open plan office?",
    "Is a TMV required on all hot water outlets under NCC?",
    "What are the backflow prevention requirements for a commercial kitchen?",
    "Size a copper pipe for 12 private WCs and 12 basins",
    "What does AS/NZS 3666 require for cooling tower water treatment?",
    "What is the maximum temperature differential for natural ventilation per AS 1668.4?",
]

_DISCLAIMER = (
    "All outputs must be verified by the responsible engineer. "
    "Clause references require validation against current standard editions."
)

# ── Session state ─────────────────────────────────────────────────────────────

def _init_session_state() -> None:
    """Initialise all session state keys on first page load."""
    defaults: dict = {
        "messages": [],
        "agent": None,
        "agent_ready": False,
        "agent_error": None,   # str | None -- holds last build error message
        "pending_prompt": None, # str | None -- set by suggestion buttons
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# ── Agent initialisation ──────────────────────────────────────────────────────

def _build_agent_if_needed() -> None:
    """Build the ReActAgent on first call and cache it in session state.

    Uses a spinner so the user sees feedback during the 10-30 second startup.
    Errors (missing API key, import errors) are caught and stored in
    st.session_state.agent_error for display in the sidebar status panel.
    """
    if st.session_state.agent_ready:
        return

    with st.spinner("Loading knowledge base and initialising agent..."):
        try:
            from agent.orchestrator import build_agent
            st.session_state.agent = build_agent()
            st.session_state.agent_ready = True
            st.session_state.agent_error = None
        except EnvironmentError as exc:
            st.session_state.agent_error = str(exc)
            st.session_state.agent_ready = False
        except Exception as exc:
            st.session_state.agent_error = (
                f"Agent failed to initialise: {exc}. "
                "Check that ANTHROPIC_API_KEY is set and dependencies are installed."
            )
            st.session_state.agent_ready = False


# ── Context prefix ────────────────────────────────────────────────────────────

def _build_context_prefix(
    project_name: str,
    project_number: str,
    building_class: str,
    disciplines: list[str],
    location: str,
) -> str:
    """Build a plain-text context prefix to prepend to every agent query.

    Only non-empty / non-default fields are included so the prefix stays
    concise. An empty string is returned when no fields are filled.
    """
    parts: list[str] = []

    if project_name.strip():
        ref = project_name.strip()
        if project_number.strip():
            ref += f" ({project_number.strip()})"
        parts.append(f"Project: {ref}.")

    if building_class != "Not specified":
        parts.append(f"Building class: {building_class}.")

    if disciplines:
        parts.append(f"Discipline: {', '.join(disciplines)}.")

    if location.strip():
        parts.append(f"Location/climate zone: {location.strip()}.")

    return " ".join(parts) + (" " if parts else "")


# ── Knowledge base status ─────────────────────────────────────────────────────

def _kb_status_rows() -> list[tuple[str, bool]]:
    """Return (label, is_loaded) pairs for each knowledge base category.

    An index is considered loaded if its persist directory exists and contains
    at least one non-hidden file. This mirrors the logic in rag/indexer.py
    build_or_load_index() fast-path check.
    """
    try:
        from rag.indexer import CATEGORIES
    except Exception:
        return [("standards", False), ("design_guides", False), ("firm_knowledge", False)]

    rows: list[tuple[str, bool]] = []
    for category, (_docs_dir, index_dir) in CATEGORIES.items():
        loaded = os.path.isdir(index_dir) and any(
            f for f in os.listdir(index_dir) if not f.startswith(".")
        )
        label = category.replace("_", " ").title()
        rows.append((label, loaded))
    return rows


# ── Sidebar ───────────────────────────────────────────────────────────────────

def _render_sidebar() -> tuple[str, str, str, list[str], str]:
    """Render the sidebar and return the five project-context field values."""
    with st.sidebar:
        st.markdown("### Project Context")

        project_name = st.text_input(
            "Project Name",
            placeholder="e.g. 25 Smith St Mixed Use",
            key="sb_project_name",
        )
        project_number = st.text_input(
            "Project Number",
            placeholder="e.g. 2024-0142",
            key="sb_project_number",
        )
        building_class = st.selectbox(
            "Building Class",
            options=[
                "Not specified",
                "Class 1", "Class 2", "Class 3", "Class 4",
                "Class 5", "Class 6", "Class 7", "Class 8",
                "Class 9a", "Class 9b", "Class 9c", "Class 10",
            ],
            key="sb_building_class",
        )
        disciplines = st.multiselect(
            "Discipline",
            options=["Hydraulic", "Mechanical (HVAC)", "Fire Services", "Electrical", "Structural"],
            key="sb_disciplines",
        )
        location = st.text_input(
            "Location / Climate Zone",
            placeholder="e.g. Brisbane, Climate Zone 2",
            key="sb_location",
        )

        st.divider()

        # ── Knowledge base status ─────────────────────────────────────────────
        st.markdown("### Knowledge Base")

        if st.session_state.agent_error:
            st.error(st.session_state.agent_error, icon="⚠️")
        elif st.session_state.agent_ready:
            st.success("Agent ready", icon="✅")
        else:
            st.info("Initialising...", icon="⏳")

        for label, loaded in _kb_status_rows():
            if loaded:
                st.markdown(
                    f'<span style="color:#22c55e">&#10003; {label}</span>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<span style="color:#9ca3af">&#9675; {label} — no documents</span>',
                    unsafe_allow_html=True,
                )

        st.divider()

        # ── Controls ──────────────────────────────────────────────────────────
        if st.button("Clear Conversation", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

        st.caption(_DISCLAIMER)

    return project_name, project_number, building_class, disciplines, location


# ── Suggested questions ───────────────────────────────────────────────────────

def _render_suggested_questions() -> None:
    """Render a 2-column grid of suggested question buttons.

    Clicking a button writes the question text to
    st.session_state.pending_prompt and calls st.rerun() so the main loop
    processes it exactly like a typed chat input submission.
    """
    st.markdown("#### Try asking:")
    cols = st.columns(2)
    for i, question in enumerate(_SUGGESTED_QUESTIONS):
        col = cols[i % 2]
        with col:
            if st.button(question, key=f"suggest_{i}", use_container_width=True):
                st.session_state.pending_prompt = question
                st.rerun()


# ── Chat processing ───────────────────────────────────────────────────────────

def _process_prompt(prompt: str, context_prefix: str) -> None:
    """Handle one user turn: append to history, query the agent, store reply.

    The clean ``prompt`` (without the context prefix) is stored in message
    history and displayed in the chat. The full ``context_prefix + prompt``
    is what the agent actually receives.

    Args:
        prompt: The user's question exactly as typed / clicked.
        context_prefix: Project-context string prepended to the agent query.
    """
    # Display and store the user message
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Guard: agent not ready
    if not st.session_state.agent_ready or st.session_state.agent is None:
        error_msg = (
            st.session_state.agent_error
            or "The agent is not ready yet. Please wait for initialisation to complete."
        )
        with st.chat_message("assistant"):
            st.error(error_msg)
        st.session_state.messages.append({"role": "assistant", "content": f"Error: {error_msg}"})
        return

    # Query the agent
    full_query = context_prefix + prompt
    with st.chat_message("assistant"):
        with st.spinner("Searching knowledge base and running calculations..."):
            try:
                response = st.session_state.agent.chat(full_query)
                # ReActAgent returns an AgentChatResponse; .response is the string
                reply = str(response.response) if hasattr(response, "response") else str(response)
                st.markdown(reply)
                st.session_state.messages.append({"role": "assistant", "content": reply})
            except Exception as exc:
                err = f"An error occurred while processing your query: {exc}"
                st.error(err)
                st.session_state.messages.append({"role": "assistant", "content": f"Error: {err}"})


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    _init_session_state()

    # Build agent before rendering anything that depends on it
    _build_agent_if_needed()

    # Sidebar (must be called before main area so context values are available)
    project_name, project_number, building_class, disciplines, location = _render_sidebar()

    # ── Page header ───────────────────────────────────────────────────────────
    st.title("§ Standards Specialist")
    st.caption("NCC · AS/NZS Standards · CIBSE · BSRIA · AIRAH")

    # ── Conversation history ──────────────────────────────────────────────────
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # ── Suggested questions (empty state only) ────────────────────────────────
    if not st.session_state.messages:
        _render_suggested_questions()

    # ── Chat input ────────────────────────────────────────────────────────────
    # Check for a pending prompt from a suggestion button first, then from the
    # chat_input widget. Using a single resolution point avoids double-processing.

    typed_prompt: str | None = st.chat_input(
        "Ask a compliance question or request a calculation...",
        key="chat_input",
    )

    # Resolve which prompt to process this run (suggestion takes priority if set)
    pending = st.session_state.pop("pending_prompt", None)
    active_prompt: str | None = pending or typed_prompt

    if active_prompt:
        context_prefix = _build_context_prefix(
            project_name, project_number, building_class, disciplines, location
        )
        _process_prompt(active_prompt, context_prefix)


main()
