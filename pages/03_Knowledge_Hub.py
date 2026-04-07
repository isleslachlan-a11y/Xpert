"""
Meridian -- Knowledge Hub page.
Manage the document indexes that power the Standards Specialist.

Four tabs:
  1. Document Library  -- Browse indexed documents and index status.
  2. Upload Documents  -- Add PDFs to a knowledge base category.
  3. Index Management  -- Rebuild indexes and edit RAG configuration.
  4. Firm Rules of Thumb -- Enter text-based firm knowledge directly.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime

import streamlit as st

st.set_page_config(
    page_title="Knowledge Hub -- Meridian",
    page_icon="\U0001f5c4",
    layout="wide",
)

# ── Category metadata ─────────────────────────────────────────────────────────

_CATEGORIES: dict[str, dict] = {
    "standards": {
        "label": "Standards",
        "docs_dir": os.path.join("documents", "standards"),
        "index_dir": os.path.join("index_storage", "standards"),
        "description": "NCC Volumes 1 & 3, AS 3500 series, AS 1668 series, AS/NZS 3666.1, etc.",
        "select_label": "Standards (NCC, AS/NZS)",
    },
    "design_guides": {
        "label": "Design Guides",
        "docs_dir": os.path.join("documents", "design_guides"),
        "index_dir": os.path.join("index_storage", "design_guides"),
        "description": "CIBSE Guides A-H, BSRIA BG series, AIRAH DA manuals.",
        "select_label": "Design Guides (CIBSE, BSRIA, AIRAH)",
    },
    "firm_knowledge": {
        "label": "Firm Knowledge",
        "docs_dir": os.path.join("documents", "firm_knowledge"),
        "index_dir": os.path.join("index_storage", "firm_knowledge"),
        "description": "Rules of thumb, past calculation packs, lessons learned.",
        "select_label": "Firm Knowledge (Rules of thumb, calc packs)",
    },
}

_SELECT_TO_KEY: dict[str, str] = {
    meta["select_label"]: key for key, meta in _CATEGORIES.items()
}

_CONFIG_PATH = os.path.join("index_storage", "rag_config.json")

_DEFAULT_CONFIG = {"chunk_size": 512, "chunk_overlap": 64, "similarity_top_k": 5}


# ── Session state ─────────────────────────────────────────────────────────────

def _init_session_state() -> None:
    defaults: dict = {
        "hub_pending_rebuild": None,   # category key awaiting rebuild confirm
        "hub_upload_files": None,
        "hub_upload_category": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ── File system helpers ───────────────────────────────────────────────────────

def _list_files(directory: str, extensions: tuple[str, ...] = (".pdf", ".txt")) -> list[dict]:
    """Return a sorted list of file info dicts for files in ``directory``."""
    if not os.path.isdir(directory):
        return []
    results: list[dict] = []
    for fname in sorted(os.listdir(directory)):
        if fname.startswith("."):
            continue
        if not fname.lower().endswith(extensions):
            continue
        fpath = os.path.join(directory, fname)
        try:
            stat = os.stat(fpath)
            results.append({
                "name": fname,
                "path": fpath,
                "size_kb": stat.st_size / 1024,
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            })
        except OSError:
            pass
    return results


def _index_is_built(index_dir: str) -> bool:
    return os.path.isdir(index_dir) and any(
        f for f in os.listdir(index_dir) if not f.startswith(".")
    )


def _load_rag_config() -> dict:
    if os.path.isfile(_CONFIG_PATH):
        try:
            with open(_CONFIG_PATH, encoding="utf-8") as f:
                return {**_DEFAULT_CONFIG, **json.load(f)}
        except (json.JSONDecodeError, OSError):
            pass
    return dict(_DEFAULT_CONFIG)


def _save_rag_config(cfg: dict) -> None:
    os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


# ── Rebuild helper (wraps rag.indexer) ───────────────────────────────────────

def _run_rebuild(category: str) -> tuple[bool, str]:
    """Call rag.indexer.rebuild_index for the given category.

    Returns (success: bool, message: str).
    LlamaIndex is imported here so the page loads without it installed.
    """
    meta = _CATEGORIES[category]
    try:
        from rag.indexer import rebuild_index
        rebuild_index(meta["docs_dir"], meta["index_dir"])
        # Bust the cached agent so it reloads fresh indexes on next use
        try:
            import agent.orchestrator as orch
            orch._cached_agent = None
        except Exception:
            pass
        return True, f"Index for '{meta['label']}' rebuilt successfully."
    except EnvironmentError as exc:
        return False, f"Environment error: {exc}"
    except Exception as exc:
        return False, f"Rebuild failed: {exc}"


# ── Tab 1: Document Library ───────────────────────────────────────────────────

def _tab_document_library() -> None:
    st.subheader("Document Library")

    total_docs = 0
    total_kb = 0.0

    for key, meta in _CATEGORIES.items():
        files = _list_files(meta["docs_dir"], extensions=(".pdf",))
        total_docs += len(files)
        total_kb += sum(f["size_kb"] for f in files)

    if total_docs:
        hc1, hc2 = st.columns(2)
        hc1.metric("Total Documents", total_docs)
        hc2.metric("Total Size", f"{total_kb / 1024:.1f} MB" if total_kb > 1024
                   else f"{total_kb:.0f} KB")
    else:
        st.info(
            "No documents have been added yet. "
            "Use the **Upload Documents** tab to add PDFs.",
            icon="\u2139\ufe0f",
        )

    st.divider()

    for key, meta in _CATEGORIES.items():
        files = _list_files(meta["docs_dir"], extensions=(".pdf",))
        indexed = _index_is_built(meta["index_dir"])
        header = f"{meta['label']}  ({len(files)} document{'s' if len(files) != 1 else ''})"

        with st.expander(header, expanded=True):
            # Index status badge
            if indexed:
                st.markdown(
                    '<span style="color:#22c55e">\u2713 Index current</span>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<span style="color:#f59e0b">\u26a0 Index not built \u2014 '
                    'go to Index Management to rebuild</span>',
                    unsafe_allow_html=True,
                )

            st.caption(meta["description"])

            if not files:
                st.info("No documents loaded. Upload PDFs in the Upload tab.")
                continue

            # File list table
            import pandas as pd
            df = pd.DataFrame([
                {
                    "File": f["name"],
                    "Size": f"{f['size_kb']:.0f} KB",
                    "Modified": f["modified"],
                }
                for f in files
            ])
            st.dataframe(df, use_container_width=True, hide_index=True)


# ── Tab 2: Upload Documents ───────────────────────────────────────────────────

def _tab_upload() -> None:
    st.subheader("Add to Knowledge Base")

    st.warning(
        "\u26a0\ufe0f Ensure you have a valid licence for all uploaded standards documents. "
        "Do not upload documents you do not have the right to use.",
        icon="\u26a0\ufe0f",
    )

    category_label = st.selectbox(
        "Knowledge Base Category",
        options=[meta["select_label"] for meta in _CATEGORIES.values()],
        key="upload_category_select",
    )
    category_key = _SELECT_TO_KEY[category_label]
    docs_dir = _CATEGORIES[category_key]["docs_dir"]

    uploaded_files = st.file_uploader(
        "Upload PDF(s)",
        type=["pdf"],
        accept_multiple_files=True,
        key="upload_file_widget",
    )

    if not uploaded_files:
        st.caption(
            f"Files will be saved to: `{docs_dir}/`"
        )
        return

    st.markdown(f"**{len(uploaded_files)} file(s) ready to add** \u2192 `{docs_dir}/`")
    for uf in uploaded_files:
        size_kb = len(uf.getvalue()) / 1024
        st.caption(f"  \u2022 {uf.name}  ({size_kb:.0f} KB)")

    if st.button("Add to Knowledge Base", type="primary", key="upload_save_btn"):
        os.makedirs(docs_dir, exist_ok=True)
        progress = st.progress(0, text="Saving files...")
        saved: list[str] = []
        for i, uf in enumerate(uploaded_files):
            dest = os.path.join(docs_dir, uf.name)
            with open(dest, "wb") as f:
                f.write(uf.getvalue())
            saved.append(uf.name)
            progress.progress((i + 1) / len(uploaded_files),
                               text=f"Saved {i + 1}/{len(uploaded_files)}: {uf.name}")

        progress.empty()
        st.success(f"{len(saved)} file(s) saved to `{docs_dir}/`.", icon="\u2705")
        st.session_state.hub_pending_rebuild = category_key
        st.rerun()

    # Rebuild confirmation (shown after save)
    if st.session_state.hub_pending_rebuild == category_key:
        st.divider()
        st.markdown("**Rebuild index now?**")
        st.caption(
            "Rebuilding incorporates the new documents into the knowledge base. "
            "This may take several minutes for large collections."
        )
        c1, c2 = st.columns([1, 4])
        with c1:
            if st.button("Yes, rebuild now", type="primary", key="upload_rebuild_yes"):
                with st.spinner(f"Rebuilding {_CATEGORIES[category_key]['label']} index..."):
                    ok, msg = _run_rebuild(category_key)
                if ok:
                    st.success(msg, icon="\u2705")
                else:
                    st.error(msg, icon="\u274c")
                st.session_state.hub_pending_rebuild = None
        with c2:
            if st.button("No, rebuild later", key="upload_rebuild_no"):
                st.session_state.hub_pending_rebuild = None
                st.info(
                    "Files saved. Run **Rebuild Index** in the Index Management tab "
                    "before querying the new documents.",
                    icon="\u2139\ufe0f",
                )


# ── Tab 3: Index Management ───────────────────────────────────────────────────

def _tab_index_management() -> None:
    st.subheader("Index Management")

    st.warning(
        "Rebuilding an index may take several minutes for large document collections. "
        "The Standards Specialist agent will reload its indexes on its next query.",
        icon="\u26a0\ufe0f",
    )

    # ── Per-category status table ─────────────────────────────────────────────
    st.markdown("**Index Status**")

    for key, meta in _CATEGORIES.items():
        files = _list_files(meta["docs_dir"], extensions=(".pdf", ".txt"))
        indexed = _index_is_built(meta["index_dir"])

        # Determine last-built time from index directory mtime
        last_built = "Never"
        if indexed:
            try:
                mtime = os.path.getmtime(meta["index_dir"])
                last_built = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            except OSError:
                last_built = "Unknown"

        with st.container(border=True):
            rc1, rc2, rc3, rc4, rc5 = st.columns([2, 1, 2, 2, 1.5])
            rc1.markdown(f"**{meta['label']}**")
            rc2.metric("Docs", len(files), label_visibility="collapsed")

            if indexed:
                rc3.markdown(
                    '<span style="color:#22c55e">\u2713 Built</span>',
                    unsafe_allow_html=True,
                )
            else:
                rc3.markdown(
                    '<span style="color:#f59e0b">\u26a0 Not built</span>',
                    unsafe_allow_html=True,
                )

            rc4.caption(f"Last built: {last_built}")

            with rc5:
                if st.button(
                    "Rebuild", key=f"idx_rebuild_{key}",
                    disabled=(len(files) == 0),
                    help="No documents to index" if len(files) == 0 else "Rebuild this index",
                ):
                    with st.spinner(f"Rebuilding {meta['label']} index..."):
                        ok, msg = _run_rebuild(key)
                    if ok:
                        st.success(msg, icon="\u2705")
                    else:
                        st.error(msg, icon="\u274c")
                    st.rerun()

    st.divider()

    # ── Rebuild all ───────────────────────────────────────────────────────────
    if st.button("Rebuild All Indexes", key="idx_rebuild_all"):
        for key, meta in _CATEGORIES.items():
            files = _list_files(meta["docs_dir"], extensions=(".pdf", ".txt"))
            if not files:
                st.info(f"Skipping {meta['label']} \u2014 no documents.", icon="\u2139\ufe0f")
                continue
            with st.spinner(f"Rebuilding {meta['label']}..."):
                ok, msg = _run_rebuild(key)
            if ok:
                st.success(msg, icon="\u2705")
            else:
                st.error(msg, icon="\u274c")
        st.rerun()

    st.divider()

    # ── RAG configuration ─────────────────────────────────────────────────────
    with st.expander("Index Configuration (RAG Settings)", expanded=False):
        cfg = _load_rag_config()

        st.caption(
            "These settings control how documents are split and retrieved. "
            "Changes require a full index rebuild to take effect. "
            "Do not increase **chunk_size** above 512 \u2014 larger chunks return "
            "paragraphs instead of clauses, reducing citation accuracy."
        )

        new_chunk_size = st.number_input(
            "Chunk Size (tokens)",
            min_value=64, max_value=2048,
            value=int(cfg["chunk_size"]),
            step=64,
            key="cfg_chunk_size",
            help="Controls clause-level precision. Default: 512.",
        )
        new_chunk_overlap = st.number_input(
            "Chunk Overlap (tokens)",
            min_value=0, max_value=256,
            value=int(cfg["chunk_overlap"]),
            step=8,
            key="cfg_chunk_overlap",
            help="Prevents clauses being split across chunk boundaries. Default: 64.",
        )
        new_top_k = st.number_input(
            "Similarity Top-K",
            min_value=1, max_value=20,
            value=int(cfg["similarity_top_k"]),
            step=1,
            key="cfg_top_k",
            help="Number of chunks retrieved per query. Default: 5.",
        )

        if new_chunk_size > 512:
            st.warning(
                f"chunk_size = {new_chunk_size} exceeds the recommended maximum of 512. "
                "This will reduce clause-level retrieval precision.",
                icon="\u26a0\ufe0f",
            )

        if st.button("Save Configuration", key="cfg_save_btn"):
            updated = {
                "chunk_size": int(new_chunk_size),
                "chunk_overlap": int(new_chunk_overlap),
                "similarity_top_k": int(new_top_k),
            }
            _save_rag_config(updated)
            st.success(
                "Configuration saved to `index_storage/rag_config.json`. "
                "Rebuild all indexes for changes to take effect.",
                icon="\u2705",
            )


# ── Tab 4: Firm Rules of Thumb ────────────────────────────────────────────────

def _tab_firm_rules() -> None:
    st.subheader("Firm Rules of Thumb")
    st.caption(
        "Enter engineering knowledge directly without uploading a PDF. "
        "Saved entries are stored in `documents/firm_knowledge/` and included "
        "in the Firm Knowledge index."
    )

    firm_dir = _CATEGORIES["firm_knowledge"]["docs_dir"]
    os.makedirs(firm_dir, exist_ok=True)

    # ── Entry form ────────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("**Add New Entry**")

        title = st.text_input(
            "Title / Reference",
            placeholder="e.g. Hydraulic Design Standards v3.2",
            key="rot_title",
        )

        body = st.text_area(
            "Rules of Thumb, Preferred Configurations, or Lessons Learned",
            height=300,
            placeholder=(
                "Example:\n"
                "- Hydraulic: Always specify Class 12 backflow prevention on "
                "cooling tower makeup. AS/NZS 2845.1.\n"
                "- HVAC: Preferred chilled water delta-T is 6\u00b0C "
                "(CHWST 6\u00b0C, CHWR 12\u00b0C).\n"
                "- Lessons learned: On project 2023-047, [issue description]. "
                "Now we always [solution]."
            ),
            key="rot_body",
        )

        if st.button("Save to Knowledge Base", type="primary", key="rot_save_btn"):
            if not body.strip():
                st.warning("Enter some content before saving.", icon="\u26a0\ufe0f")
            else:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_title = (
                    title.strip().replace(" ", "_").replace("/", "-")[:40]
                    if title.strip() else "rules_of_thumb"
                )
                filename = f"{timestamp}_{safe_title}.txt"
                filepath = os.path.join(firm_dir, filename)

                header_line = f"# {title.strip()}\n" if title.strip() else ""
                meta_line = f"# Saved: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                content = header_line + meta_line + body.strip() + "\n"

                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)

                st.success(
                    f"Saved as `{filename}` in `{firm_dir}/`.",
                    icon="\u2705",
                )
                st.session_state.hub_pending_rebuild = "firm_knowledge_rot"
                st.rerun()

    # Rebuild prompt after saving rules of thumb
    if st.session_state.hub_pending_rebuild == "firm_knowledge_rot":
        st.divider()
        st.markdown("**Rebuild Firm Knowledge index now?**")
        c1, c2 = st.columns([1, 4])
        with c1:
            if st.button("Yes, rebuild", type="primary", key="rot_rebuild_yes"):
                with st.spinner("Rebuilding Firm Knowledge index..."):
                    ok, msg = _run_rebuild("firm_knowledge")
                if ok:
                    st.success(msg, icon="\u2705")
                else:
                    st.error(msg, icon="\u274c")
                st.session_state.hub_pending_rebuild = None
        with c2:
            if st.button("No, later", key="rot_rebuild_no"):
                st.session_state.hub_pending_rebuild = None

    # ── Existing entries ──────────────────────────────────────────────────────
    st.divider()
    txt_files = _list_files(firm_dir, extensions=(".txt",))

    if not txt_files:
        st.info(
            "No text entries yet. Add your first rule of thumb above.",
            icon="\u2139\ufe0f",
        )
        return

    st.markdown(f"**Existing Entries ({len(txt_files)} files)**")

    for finfo in txt_files:
        with st.expander(f"{finfo['name']}  \u2014  {finfo['modified']}  ({finfo['size_kb']:.1f} KB)"):
            try:
                with open(finfo["path"], encoding="utf-8") as f:
                    content = f.read()
                st.text(content)
            except OSError as exc:
                st.error(f"Could not read file: {exc}")

            col_del, _ = st.columns([1, 4])
            with col_del:
                if st.button(
                    "\U0001f5d1 Delete",
                    key=f"rot_del_{finfo['name']}",
                    help="Permanently delete this entry",
                ):
                    try:
                        os.remove(finfo["path"])
                        st.success(f"Deleted `{finfo['name']}`.", icon="\u2705")
                        st.rerun()
                    except OSError as exc:
                        st.error(f"Delete failed: {exc}", icon="\u274c")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    _init_session_state()

    st.title("\U0001f5c4 Knowledge Hub")
    st.caption("Manage your firm's engineering knowledge base")

    tabs = st.tabs([
        "Document Library",
        "Upload Documents",
        "Index Management",
        "Firm Rules of Thumb",
    ])

    with tabs[0]:
        _tab_document_library()

    with tabs[1]:
        _tab_upload()

    with tabs[2]:
        _tab_index_management()

    with tabs[3]:
        _tab_firm_rules()


main()
