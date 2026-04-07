# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Project Identity

**Product name:** Meridian (codebase root: `Xpert/`)
**Purpose:** A discipline-specialist AI assistant for building services engineers — answers compliance questions with clause citations, performs engineering calculations, and manages firm-specific knowledge.

Three integrated capabilities served from a single Streamlit app:
1. **Standards Specialist** — RAG-powered agent on NCC, AS/NZS, CIBSE, BSRIA, AIRAH documents. Cites exact clauses. Never fabricates.
2. **Calculator Library** — Python calculators for pipe sizing, ventilation, psychrometrics, drainage, heat load.
3. **Firm Knowledge Hub** — Separate vector index for firm-specific rules of thumb, past calc packs.

---

## Tech Stack — Do Not Deviate

| Layer | Technology | Version |
|---|---|---|
| Frontend | Streamlit | ≥1.32 |
| LLM | Anthropic Claude API | `claude-sonnet-4-6` — always, never Opus, never GPT |
| Agent framework | LlamaIndex ReActAgent | ≥0.10 |
| Embeddings | HuggingFace BGE | `BAAI/bge-small-en-v1.5` — free, local, no API cost |
| Vector store | LlamaIndex SimpleVectorStore | Built-in — no external DB |
| PDF processing | LlamaIndex SimpleDirectoryReader | Built-in |
| Calculations | Pure Python | ≥3.11 |
| Env management | python-dotenv | Current |

**Why `bge-small-en-v1.5`:** Runs locally, no per-token cost. Index built once and reused.
**Why `claude-sonnet-4-6`:** Cost-performance balance for daily engineering use. Do not substitute.

---

## Running the Project

```bash
# First time setup
cd meridian
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env — add ANTHROPIC_API_KEY

# Build document indexes (after adding PDFs to documents/)
python -c "from rag.indexer import build_index; build_index()"

# Rebuild a specific index only
python -c "from rag.indexer import rebuild_index; rebuild_index('documents/standards', 'index_storage/standards')"

# Launch
streamlit run app.py

# LAN access
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

**Required environment variable:**
```
ANTHROPIC_API_KEY=sk-ant-...
```

---

## Project Structure

```
meridian/
├── app.py                          # Streamlit entry point — home screen only
├── config.py                       # Central config dataclass, loaded from .env
├── .env                            # NEVER commit
├── .env.example                    # Commit this — template only
│
├── pages/
│   ├── 01_Standards_Specialist.py  # Chat interface — primary product page
│   ├── 02_Calculators.py           # Structured calculator forms
│   └── 03_Knowledge_Hub.py         # Document upload + index management
│
├── agent/
│   ├── orchestrator.py             # build_agent() — assembles the ReActAgent
│   ├── prompts.py                  # SYSTEM_PROMPT — most important file, edit frequently
│   └── tools.py                    # ALL_CALC_TOOLS as FunctionTools
│
├── rag/
│   ├── indexer.py                  # build_or_load_index(), rebuild_index(), load_all_indexes()
│   └── retriever.py
│
├── calculators/
│   ├── ventilation_natural.py      # AS 1668.4—2012
│   ├── ventilation_mechanical.py   # AS 1668.2
│   ├── pipe_sizing.py              # AS 3500.1
│   ├── hot_water.py                # AS 3500.4
│   ├── drainage.py                 # AS 3500.2
│   ├── stormwater.py               # AS 3500.3
│   └── psychrometrics.py           # AIRAH DA09
│
├── documents/                      # Licensed PDFs — NEVER commit
│   ├── standards/
│   ├── design_guides/
│   └── firm_knowledge/
│
└── index_storage/                  # Auto-generated vector indexes — NEVER commit
    ├── standards/
    ├── design_guides/
    └── firm_knowledge/
```

---

## Agent Architecture

**Type:** LlamaIndex ReActAgent (Reason → Act → Observe loop)

**Tools available to the agent:**
1. `standards_knowledge_base` — QueryEngineTool on standards index
2. `design_guides_knowledge_base` — QueryEngineTool on design guides index
3. `firm_knowledge_base` — QueryEngineTool on firm knowledge index
4. All calculation tools from `ALL_CALC_TOOLS` in `agent/tools.py`

**Max iterations: 12** — do not reduce. Complex compliance + calculation queries require multiple tool calls.

**Agent caching is mandatory** — `build_agent()` loads all three indexes (10–30 seconds). Cache in a module-level variable:

```python
_cached_agent = None

def build_agent():
    global _cached_agent
    if _cached_agent is not None:
        return _cached_agent
    # ... build ...
    _cached_agent = agent
    return agent
```

The agent lives in `st.session_state.agent`. It is built once on first page load inside `st.spinner("Loading knowledge base...")`. Never call `build_agent()` outside session state initialisation.

---

## RAG Configuration — These Numbers Are Deliberate

```python
Settings.chunk_size = 512       # Smaller = clause-level precision
Settings.chunk_overlap = 64     # Prevents clause text split across chunks
similarity_top_k = 5            # 5 most relevant chunks per query
```

Do not increase `chunk_size` above 512 — larger chunks return paragraphs, not clauses, defeating the purpose.

**Three separate indexes** (not one) allow the agent to know which knowledge base it's drawing from and allow independent rebuilds when one category's documents are updated.

---

## System Prompt — `agent/prompts.py`

`SYSTEM_PROMPT` encodes the agent's behaviour contract. Key rules:

1. Always search the knowledge base before answering compliance questions
2. Cite every clause: `[AS 1668.2 Cl. 4.3.2]` format — never omit
3. If not found in indexed documents, say so explicitly — **never fabricate clause numbers**
4. Distinguish DTS provisions from Performance Solution pathways
5. Flag when site-specific assessment or peer review is required
6. Apply Australian context — climate zones, state NCC amendments
7. SI units throughout: kPa, L/s, kW, °C, mm, m
8. Label rules of thumb as preliminary estimates requiring verification
9. Flag cross-discipline impacts (hydraulic → mechanical → fire)
10. Include WHS implications for installation and commissioning

**Output format rules in the prompt:**
- Compliance queries: Requirement → Clause → Exceptions → Key Notes
- Calculations: Method → Inputs → Working → Result → Assumptions
- Design guidance: Recommendation → Justification → Alternatives → Risks
- Complex responses end with a **Key Actions** bullet list

---

## Calculator Standards Mapping

| Calculator | Standard | Key clauses |
|---|---|---|
| `ventilation_natural.py` | AS 1668.4—2012 | Cl. 3.4 (Simple), Cl. 3.2.1/2/3 (arrangements) |
| `ventilation_mechanical.py` | AS 1668.2 | Table 2 (rates), Cl. 4.3 (OA qty), Section 6 (carpark) |
| `pipe_sizing.py` | AS 3500.1—2018 | Table 3.1 (FU), Table 3.2 (FU→flow), Cl. 3.4.3 (velocity), Cl. 7.4.1 (pressure) |
| `hot_water.py` | AS 3500.4 | Cl. 4.2 (storage), Cl. 6.5 (TMV), SA HB 39 |
| `drainage.py` | AS 3500.2 | DDU method, Table 3.1, Cl. 3.3 (grades) |
| `stormwater.py` | AS 3500.3 | Rational method Q=CIA/360 |
| `psychrometrics.py` | AIRAH DA09 Section 9 | Carrier Simplified Method, Equations 4–36, Figure 9.15 |

**Critical constants — do not change without checking the standard:**
- Pipe velocity limit: **3.0 m/s** (AS 3500.1 Cl. 3.4.3)
- Minimum residual pressure: **100 kPa** at furthest outlet (AS 3500.1 Cl. 7.4.1)
- Hot water storage: **≥60°C** (legionella risk)
- TMV outlet temp: **≤50°C** (AS 3500.4 Cl. 6.5)
- Carpark ventilation: **6 ACH minimum** or CO-controlled (AS 1668.2 Cl. 6.3)
- Office OA rate: **10 L/s/person + 0.5 L/s/m²** (AS 1668.2 Table 2)
- Psychrometric air density: **1.20** (OASH = 1.20 × L/s × ΔT)
- Psychrometric latent: **3.0** (OALH = 3.0 × L/s × Δw)

---

## Calculators Already Built — Do Not Rebuild

Two calculators exist as complete HTML files. When implementing their Python equivalents, port the exact methodology:

**`AS1668_4_Ventilation_Calculator.html`** — AS 1668.4—2012 Simple Procedure (Cl. 3.4)
- Three arrangements: Direct (Cl. 3.2.1), Borrowed (Cl. 3.2.2), Flowthrough (Cl. 3.2.3)
- Safety factors: Class 1/2/4 = 5%, Class 5–9 = 10%, Classroom <16yrs = 12.5%
- Borrowed: internal opening = 2 × pct × area_B; external = pct × (area_A + area_B)
- Flowthrough: each external ≥ pct × total combined area; internal per Cl. 2.4.4

**`DA09_Psychrometric_Calculator.html`** — AIRAH DA09 Carrier Simplified Method
- Psychrometric properties via ASHRAE Magnus equations + Sprung psychrometer formula
- ADP computed iteratively — ESHF line intersection with saturation curve
- Case detection: general cooling / high latent (ADP < 5°C) / reheat (ESHF < 0.65) / 100% OA
- Key equations: ERSH (Eq.4), ERLH (Eq.5), ERTH (Eq.6), ESHF (Eq.26), L/s_DA (Eq.36), EDB (Eq.31), LDB (Eq.32)

---

## Streamlit Conventions

- Initialise all session state keys in a single `_init_session_state()` at the top of each page
- `st.session_state.messages` = list of `{"role": str, "content": str}` dicts; role is `"user"` or `"assistant"`
- Context injection on Standards Specialist page — prepend project context to agent query, display clean user prompt in chat:

```python
context = f"Project: {proj_name}. Building class: {bldg_class}. Discipline: {discipline}. "
full_query = context + user_prompt
response = agent.chat(full_query)
# Show user_prompt in chat, not full_query
```

- Wrap every `agent.chat()` in try/except; display `st.error(str(e))` — never show raw tracebacks
- Only call `st.rerun()` when genuinely necessary

---

## Adding a New Calculator

1. Create `calculators/{name}.py` with pure Python functions
2. Every function returns a dict with a `clause_ref` key citing the standard
3. Add `format_{name}_result(result: dict) -> str` for agent-readable output
4. Add a `__main__` block with a worked example
5. Wrap as a `FunctionTool` in `agent/tools.py` with a clear, specific tool description
6. Add to `ALL_CALC_TOOLS`
7. Add a tab in `pages/02_Calculators.py`
8. Update the Calculator Standards Mapping table in this file

## Adding Documents to the Knowledge Base

1. Place licensed PDFs in the correct `documents/` subfolder
2. Run: `python -c "from rag.indexer import rebuild_index; rebuild_index('documents/standards', 'index_storage/standards')"`
3. Restart the Streamlit app
4. Test with 3–5 queries targeting the new document
5. Update the Document Priority list below

**Document indexing priority (Phase 1):** NCC Vol. 1, NCC Vol. 3, AS 1668.2, AS 1668.4, AS 3500.1, AS 3500.2, AS/NZS 3666.1, AIRAH DA09

**Phase 3 design guides:** CIBSE A/B/C/F/G/H; BSRIA BG 29/50/2/6/45; AIRAH DA17/DA19/DA20

---

## Hard Constraints

- **Never commit** `.env`, `documents/`, `index_storage/`
- **Never use** a model other than `claude-sonnet-4-6`
- **Never increase** `chunk_size` above 512 without testing
- **Never call** `build_agent()` outside session state initialisation
- **Never use** `WidthType.PERCENTAGE` in docx output — breaks in Google Docs
- **Never use** unicode bullet characters in docx — use `LevelFormat.BULLET`
- **Never store** user data or project details permanently — Meridian is stateless per session
