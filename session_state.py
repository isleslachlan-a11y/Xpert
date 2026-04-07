"""
Meridian -- Shared session state key constants and initialiser.

All Streamlit session state keys used across any page are defined here as
string constants. This prevents typo-driven key mismatches and provides a
single place to audit what state the application maintains.

Usage in a page::

    from session_state import init_all

    def _init_session_state() -> None:
        init_all()

Pages may call init_all() safely on every run -- keys already present in
st.session_state are never overwritten.
"""

from __future__ import annotations

# ── Key constants ─────────────────────────────────────────────────────────────
# Grouped by owning page / concern.

# --- Standards Specialist (pages/01) -----------------------------------------
KEY_AGENT = "agent"                   # ReActAgent instance | None
KEY_AGENT_READY = "agent_ready"       # bool
KEY_AGENT_ERROR = "agent_error"       # str | None -- last build error message
KEY_MESSAGES = "messages"             # list[{"role": str, "content": str}]
KEY_PENDING_PROMPT = "pending_prompt" # str | None -- set by suggestion buttons

# --- Calculator Library (pages/02) -------------------------------------------
KEY_PIPE_RESULT = "pipe_result"           # dict | None
KEY_VENT_ZONES = "vent_zones"             # list[dict]
KEY_VENT_RESULT = "vent_result"           # dict | None
KEY_HW_STORAGE_RESULT = "hw_storage_result"  # dict | None
KEY_HW_TMV_RESULT = "hw_tmv_result"          # dict | None
KEY_SW_FLOW_RESULT = "sw_flow_result"        # dict | None
KEY_SW_PIPE_RESULT = "sw_pipe_result"        # dict | None

# --- Knowledge Hub (pages/03) ------------------------------------------------
KEY_HUB_PENDING_REBUILD = "hub_pending_rebuild"  # str | None -- category key awaiting confirm

# ── Default values ────────────────────────────────────────────────────────────

_DEFAULTS: dict[str, object] = {
    # Standards Specialist
    KEY_AGENT: None,
    KEY_AGENT_READY: False,
    KEY_AGENT_ERROR: None,
    KEY_MESSAGES: [],
    KEY_PENDING_PROMPT: None,
    # Calculator Library
    KEY_PIPE_RESULT: None,
    KEY_VENT_ZONES: [
        {
            "name": "Zone 1",
            "space_type": "office_open_plan",
            "floor_area_m2": 100.0,
            "occupants": None,
        }
    ],
    KEY_VENT_RESULT: None,
    KEY_HW_STORAGE_RESULT: None,
    KEY_HW_TMV_RESULT: None,
    KEY_SW_FLOW_RESULT: None,
    KEY_SW_PIPE_RESULT: None,
    # Knowledge Hub
    KEY_HUB_PENDING_REBUILD: None,
}


def init_all() -> None:
    """Initialise all session state keys with their default values.

    Safe to call on every page run -- only sets keys that are not already
    present. Existing values are never overwritten.

    Must be called after ``import streamlit as st`` is in scope for the caller.
    """
    import streamlit as st

    for key, default in _DEFAULTS.items():
        if key not in st.session_state:
            # Use a copy for mutable defaults to prevent shared-reference bugs
            if isinstance(default, list):
                st.session_state[key] = list(default)
            elif isinstance(default, dict):
                st.session_state[key] = dict(default)
            else:
                st.session_state[key] = default


def reset_chat() -> None:
    """Clear the Standards Specialist conversation history."""
    import streamlit as st
    st.session_state[KEY_MESSAGES] = []


def reset_calculator_results() -> None:
    """Clear all calculator result keys (does not reset zone schedule)."""
    import streamlit as st
    for key in (
        KEY_PIPE_RESULT,
        KEY_VENT_RESULT,
        KEY_HW_STORAGE_RESULT,
        KEY_HW_TMV_RESULT,
        KEY_SW_FLOW_RESULT,
        KEY_SW_PIPE_RESULT,
    ):
        st.session_state[key] = None
