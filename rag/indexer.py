"""
Meridian — Vector index builder and loader.
Uses LlamaIndex SimpleDirectoryReader + SimpleVectorStore with local BGE embeddings.

RAG settings (do not change without testing):
  chunk_size=512    — clause-level precision; larger chunks return paragraphs, not clauses
  chunk_overlap=64  — prevents clause text being split across chunk boundaries
  top_k=5           — 5 most relevant chunks per query (used by retriever.py / orchestrator.py)

Module-level Settings are configured once on import. All downstream LlamaIndex components
(SimpleDirectoryReader, VectorStoreIndex) inherit these automatically.
"""

from __future__ import annotations

import os
import shutil
import warnings
from typing import Optional

from dotenv import load_dotenv
from llama_index.core import (
    Settings,
    SimpleDirectoryReader,
    StorageContext,
    VectorStoreIndex,
    load_index_from_storage,
)
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.anthropic import Anthropic

load_dotenv()

# ── Module-level LlamaIndex settings ──────────────────────────────────────────
# Configured once on import. Do NOT move these into individual functions —
# LlamaIndex reads Settings at node-parsing time, not at query time.

Settings.llm = Anthropic(
    model="claude-sonnet-4-6",
    max_tokens=4096,
    api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
)

Settings.embed_model = HuggingFaceEmbedding(
    model_name="BAAI/bge-small-en-v1.5",
)

Settings.chunk_size = 512   # Clause-level precision — do not increase above 512
Settings.chunk_overlap = 64


# ── Index paths — mirrors config.py but avoids a circular import ───────────────
_DOCS_ROOT = "documents"
_INDEX_ROOT = "index_storage"

CATEGORIES: dict[str, tuple[str, str]] = {
    "standards": (
        os.path.join(_DOCS_ROOT, "standards"),
        os.path.join(_INDEX_ROOT, "standards"),
    ),
    "design_guides": (
        os.path.join(_DOCS_ROOT, "design_guides"),
        os.path.join(_INDEX_ROOT, "design_guides"),
    ),
    "firm_knowledge": (
        os.path.join(_DOCS_ROOT, "firm_knowledge"),
        os.path.join(_INDEX_ROOT, "firm_knowledge"),
    ),
}


def build_or_load_index(
    docs_dir: str,
    index_dir: str,
) -> Optional[VectorStoreIndex]:
    """Build a new vector index or load an existing one from disk.

    Decision logic:
    - If ``index_dir`` exists and contains at least one file, the persisted index
      is loaded from disk — no documents are re-read and no embeddings are
      re-computed.
    - Otherwise, all ``.pdf`` files under ``docs_dir`` (recursive) are read with
      ``SimpleDirectoryReader``, a ``VectorStoreIndex`` is built, and the result
      is persisted to ``index_dir`` for future loads.

    Args:
        docs_dir: Path to the folder containing source PDF documents.
        index_dir: Path where the persisted index is stored / will be written.

    Returns:
        A ``VectorStoreIndex`` instance, or ``None`` if ``docs_dir`` contains no
        PDF files (e.g. the folder is empty during development).
    """
    # ── Fast path: load persisted index ──────────────────────────────────────
    if os.path.isdir(index_dir) and any(
        fname for fname in os.listdir(index_dir) if not fname.startswith(".")
    ):
        print(f"  Loading existing index from '{index_dir}' ...")
        storage_context = StorageContext.from_defaults(persist_dir=index_dir)
        index = load_index_from_storage(storage_context)
        print(f"  Index loaded from '{index_dir}'.")
        return index

    # ── Slow path: build from documents ──────────────────────────────────────
    if not os.path.isdir(docs_dir):
        warnings.warn(
            f"Documents directory '{docs_dir}' does not exist. "
            "Create it and add PDF files before building an index.",
            stacklevel=2,
        )
        return None

    pdf_files = [
        f for f in _walk_files(docs_dir) if f.lower().endswith(".pdf")
    ]

    if not pdf_files:
        warnings.warn(
            f"No PDF files found in '{docs_dir}'. "
            "Add licensed PDFs to this folder then run rebuild_index().",
            stacklevel=2,
        )
        return None

    print(f"  Reading {len(pdf_files)} PDF(s) from '{docs_dir}' ...")
    reader = SimpleDirectoryReader(
        input_dir=docs_dir,
        recursive=True,
        required_exts=[".pdf"],
    )
    documents = reader.load_data()
    print(f"  Loaded {len(documents)} document chunks. Building index ...")

    index = VectorStoreIndex.from_documents(documents, show_progress=True)

    os.makedirs(index_dir, exist_ok=True)
    index.storage_context.persist(persist_dir=index_dir)
    print(f"  Index built and persisted to '{index_dir}'.")

    return index


def rebuild_index(
    docs_dir: str,
    index_dir: str,
) -> Optional[VectorStoreIndex]:
    """Force a full rebuild of the index by deleting any existing persisted data.

    Use this after adding new PDF documents to ``docs_dir``. The existing index
    at ``index_dir`` is deleted unconditionally before re-reading documents.

    Args:
        docs_dir: Path to the folder containing source PDF documents.
        index_dir: Path to the persisted index to delete and rebuild.

    Returns:
        A freshly built ``VectorStoreIndex``, or ``None`` if no PDFs were found.
    """
    if os.path.isdir(index_dir):
        print(f"  Removing existing index at '{index_dir}' ...")
        shutil.rmtree(index_dir)
        print(f"  Existing index removed.")

    print(f"  Building new index from '{docs_dir}' ...")
    index = build_or_load_index(docs_dir, index_dir)

    if index is not None:
        print(f"  Rebuild complete for '{index_dir}'.")
    else:
        print(f"  Rebuild skipped — no documents in '{docs_dir}'.")

    return index


def load_all_indexes() -> dict[str, Optional[VectorStoreIndex]]:
    """Load all three knowledge-base indexes.

    Attempts to load each index category (standards, design_guides, firm_knowledge).
    Categories with no persisted index and no source documents return ``None``
    without raising an exception — this is expected during development before
    documents have been added.

    Returns:
        A dict with keys ``"standards"``, ``"design_guides"``, ``"firm_knowledge"``.
        Each value is a ``VectorStoreIndex`` if the index exists, or ``None``.

    Example::

        indexes = load_all_indexes()
        if indexes["standards"] is not None:
            query_engine = indexes["standards"].as_query_engine(similarity_top_k=5)
    """
    result: dict[str, Optional[VectorStoreIndex]] = {}

    for category, (docs_dir, index_dir) in CATEGORIES.items():
        print(f"Loading '{category}' index ...")
        result[category] = build_or_load_index(docs_dir, index_dir)

    loaded = [k for k, v in result.items() if v is not None]
    empty = [k for k, v in result.items() if v is None]

    if loaded:
        print(f"Indexes ready: {', '.join(loaded)}")
    if empty:
        print(f"No documents yet for: {', '.join(empty)} (add PDFs and run rebuild_index)")

    return result


# ── Internal helpers ───────────────────────────────────────────────────────────

def _walk_files(root: str) -> list[str]:
    """Return all file paths under ``root``, recursively."""
    found: list[str] = []
    for dirpath, _, filenames in os.walk(root):
        for filename in filenames:
            found.append(os.path.join(dirpath, filename))
    return found


# ── CLI entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Meridian — building document indexes")
    print("=" * 50)

    for _category, (_docs_dir, _index_dir) in CATEGORIES.items():
        print(f"\n[{_category.upper()}]")
        build_or_load_index(_docs_dir, _index_dir)

    print("\n" + "=" * 50)
    print("Done. Launch the app with: streamlit run app.py")
