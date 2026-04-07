"""
Meridian — Engineering AI Assistant
Streamlit multi-page application entry point.
"""

import streamlit as st

st.set_page_config(
    page_title="Meridian",
    page_icon="§",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _init_session_state() -> None:
    if "initialised" not in st.session_state:
        st.session_state.initialised = True


def _render_sidebar() -> None:
    with st.sidebar:
        st.markdown("# § MERIDIAN")
        st.caption("Engineering AI Assistant")
        st.divider()
        st.page_link("pages/01_Standards_Specialist.py", label="Standards Specialist", icon="📋")
        st.page_link("pages/02_Calculators.py", label="Calculator Library", icon="🔢")
        st.page_link("pages/03_Knowledge_Hub.py", label="Knowledge Hub", icon="📚")
        st.divider()
        st.caption("Building Services AI — Australian Standards")


def _render_home() -> None:
    st.title("§ Meridian")
    st.subheader("Engineering AI Assistant")
    st.markdown(
        "Discipline-specialist AI for building services engineers. "
        "Compliance answers with clause citations. Calculations with auditable methodology."
    )
    st.divider()

    col1, col2, col3 = st.columns(3)

    with col1:
        with st.container(border=True):
            st.markdown("### 📋 Standards Specialist")
            st.markdown(
                "Ask compliance questions across NCC, AS/NZS standards, CIBSE Guides, "
                "BSRIA design guides and AIRAH DA series. Every answer cites the exact clause."
            )
            st.page_link("pages/01_Standards_Specialist.py", label="Open Standards Specialist →")

    with col2:
        with st.container(border=True):
            st.markdown("### 🔢 Calculator Library")
            st.markdown(
                "Pipe sizing, ventilation, psychrometrics, drainage, heat load — "
                "each with auditable methodology and printable output."
            )
            st.page_link("pages/02_Calculators.py", label="Open Calculator Library →")

    with col3:
        with st.container(border=True):
            st.markdown("### 📚 Knowledge Hub")
            st.markdown(
                "Upload firm-specific rules of thumb, past calculation packs and preferred "
                "configurations. Creates institutional knowledge your team can query."
            )
            st.page_link("pages/03_Knowledge_Hub.py", label="Open Knowledge Hub →")


def main() -> None:
    _init_session_state()
    _render_sidebar()
    _render_home()


if __name__ == "__main__":
    main()
