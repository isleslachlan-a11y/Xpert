"""
Meridian — Agent orchestrator.
Assembles the LlamaIndex ReActAgent with all knowledge base tools and calculator tools.

The agent is cached at module level after the first call. Building it loads all three
vector indexes and downloads the embedding model on the first run (10–30 seconds).
Never call build_agent() outside of st.session_state initialisation in a Streamlit page.
"""

from __future__ import annotations

import os
import warnings

from dotenv import load_dotenv
from llama_index.core.agent import ReActAgent
from llama_index.core.tools import QueryEngineTool, ToolMetadata
from llama_index.llms.anthropic import Anthropic

from agent.prompts import SYSTEM_PROMPT
from agent.tools import ALL_CALC_TOOLS
from config import get_config
from rag.indexer import load_all_indexes

load_dotenv()

_cached_agent: ReActAgent | None = None

# ── Knowledge base tool definitions ───────────────────────────────────────────
# Descriptions are deliberately specific — the ReAct agent reads these to decide
# which tool to call. Vague descriptions cause the wrong tool to be selected.

_KB_TOOL_METADATA: dict[str, ToolMetadata] = {
    "standards": ToolMetadata(
        name="standards_knowledge_base",
        description=(
            "Search NCC Volumes 1 and 3, AS 3500 series, AS 1668 series, AS/NZS 3666.1 "
            "and other Australian/NZ standards for compliance requirements, clause numbers, "
            "DTS provisions, and deemed-to-satisfy criteria. "
            "Use this tool for any question of the form 'is this allowed', "
            "'what does the standard say', 'what is the minimum requirement', "
            "'which clause covers', or 'does this comply with'."
        ),
    ),
    "design_guides": ToolMetadata(
        name="design_guides_knowledge_base",
        description=(
            "Search AIRAH DA manuals (DA09, DA17, DA19, DA20), CIBSE Guides (A, B, C, F, G, H), "
            "and BSRIA design guides for engineering methodology, sizing rules of thumb, "
            "best-practice design approaches, and performance benchmarks. "
            "Use this tool for 'how should I design', 'what is the recommended approach', "
            "'what rule of thumb applies', or 'what does CIBSE / AIRAH recommend' questions."
        ),
    ),
    "firm_knowledge": ToolMetadata(
        name="firm_knowledge_base",
        description=(
            "Search firm-specific rules of thumb, lessons learned from past projects, "
            "preferred equipment configurations, and internal design standards. "
            "Use this tool when the question involves preferred practice, firm defaults, "
            "past project experience, or internal quality requirements."
        ),
    ),
}


def build_agent() -> ReActAgent:
    """Build and return the Meridian ReActAgent, using a module-level cache.

    On the first call this function:
    1. Loads all three vector indexes via ``rag.indexer.load_all_indexes()``.
    2. Wraps each non-None index as a ``QueryEngineTool`` with ``similarity_top_k=5``.
    3. Appends all calculator tools from ``agent.tools.ALL_CALC_TOOLS``.
    4. Instantiates the Anthropic LLM with the project system prompt.
    5. Creates and caches a ``ReActAgent`` with ``max_iterations=12``.

    Subsequent calls return the cached agent immediately without rebuilding.

    Returns:
        A ready-to-use ``ReActAgent`` instance.

    Raises:
        EnvironmentError: If ``ANTHROPIC_API_KEY`` is not set in the environment.
        RuntimeError: If agent assembly fails for any other reason.
    """
    global _cached_agent
    if _cached_agent is not None:
        return _cached_agent

    cfg = get_config()

    # ── Validate API key early ────────────────────────────────────────────────
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY is not set. "
            "Add it to your .env file and restart the application."
        )

    try:
        # ── Load knowledge base indexes ───────────────────────────────────────
        indexes = load_all_indexes()

        tools: list = []

        # ── Wrap each index as a QueryEngineTool ──────────────────────────────
        for category, index in indexes.items():
            if index is None:
                warnings.warn(
                    f"No documents indexed for '{category}'. "
                    f"The '{_KB_TOOL_METADATA[category].name}' tool will not be available "
                    "until PDFs are added and the index is built.",
                    stacklevel=2,
                )
                continue

            query_engine = index.as_query_engine(
                similarity_top_k=cfg.SIMILARITY_TOP_K,
            )
            tools.append(
                QueryEngineTool(
                    query_engine=query_engine,
                    metadata=_KB_TOOL_METADATA[category],
                )
            )

        # ── Add calculator tools ──────────────────────────────────────────────
        tools.extend(ALL_CALC_TOOLS)

        if not tools:
            warnings.warn(
                "No tools are available (no indexed documents and no calculator tools). "
                "The agent will answer from its base training only.",
                stacklevel=2,
            )

        # ── Instantiate LLM ───────────────────────────────────────────────────
        llm = Anthropic(
            model=cfg.MODEL_NAME,
            api_key=api_key,
            max_tokens=cfg.MAX_TOKENS,
            system_prompt=SYSTEM_PROMPT,
        )

        # ── Assemble the ReActAgent ───────────────────────────────────────────
        agent = ReActAgent.from_tools(
            tools=tools,
            llm=llm,
            verbose=False,
            max_iterations=12,
        )

        _cached_agent = agent
        return _cached_agent

    except EnvironmentError:
        raise
    except Exception as exc:
        raise RuntimeError(
            f"Failed to build Meridian agent: {exc}"
        ) from exc
