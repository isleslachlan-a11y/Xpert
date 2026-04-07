"""
Meridian -- Central configuration.
All settings are loaded from environment variables via python-dotenv.
Import `get_config()` to access the singleton Config instance.

If ANTHROPIC_API_KEY is not set, `get_config()` returns a Config with an empty
key and prints a warning -- it does NOT raise an exception at import time.
The missing key is detected and reported at agent-build time instead, so the
Streamlit UI can start and display a helpful error rather than crashing on load.
"""

from __future__ import annotations

import os
import warnings
from dataclasses import dataclass, field
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    # ── LLM ──────────────────────────────────────────────────────────────────
    ANTHROPIC_API_KEY: str = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", "")
    )
    MODEL_NAME: str = "claude-sonnet-4-6"
    MAX_TOKENS: int = 4096

    # ── RAG ──────────────────────────────────────────────────────────────────
    CHUNK_SIZE: int = 512       # Do NOT increase above 512 -- clause-level precision
    CHUNK_OVERLAP: int = 64
    SIMILARITY_TOP_K: int = 5

    # ── Paths ─────────────────────────────────────────────────────────────────
    DOCS_DIR: str = "documents"
    INDEX_DIR: str = "index_storage"

    # ── Derived paths (read-only convenience) ────────────────────────────────
    @property
    def standards_docs(self) -> str:
        return os.path.join(self.DOCS_DIR, "standards")

    @property
    def design_guides_docs(self) -> str:
        return os.path.join(self.DOCS_DIR, "design_guides")

    @property
    def firm_knowledge_docs(self) -> str:
        return os.path.join(self.DOCS_DIR, "firm_knowledge")

    @property
    def standards_index(self) -> str:
        return os.path.join(self.INDEX_DIR, "standards")

    @property
    def design_guides_index(self) -> str:
        return os.path.join(self.INDEX_DIR, "design_guides")

    @property
    def firm_knowledge_index(self) -> str:
        return os.path.join(self.INDEX_DIR, "firm_knowledge")

    def validate(self) -> None:
        """Raise EnvironmentError if required settings are missing."""
        if not self.ANTHROPIC_API_KEY:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY is not set. "
                "Copy .env.example to .env and add your key, then restart."
            )


@lru_cache(maxsize=1)
def get_config() -> Config:
    """Return the singleton Config instance.

    Does not raise on a missing API key -- call ``cfg.validate()`` explicitly
    when the key is actually needed (i.e. in ``agent.orchestrator.build_agent``).
    """
    cfg = Config()
    if not cfg.ANTHROPIC_API_KEY:
        warnings.warn(
            "ANTHROPIC_API_KEY is not set. "
            "The Standards Specialist agent will not start until this is configured. "
            "See .env.example for setup instructions.",
            stacklevel=2,
        )
    return cfg
