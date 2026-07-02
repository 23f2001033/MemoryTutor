# MemoryTutor — Implementation Plan

An AI study tutor with persistent memory across sessions, built on [Cognee](https://docs.cognee.ai) + Google Gemini + Streamlit.

This plan is the implementation spec. Facts marked **[verified]** were checked against the Cognee docs and PyPI (cognee 1.2.2, June 2026). Anything marked **[verify at impl time]** must be confirmed against the installed package before relying on it.

---

## 1. Problem & Solution (for README framing)

- **Problem — AI amnesia:** Chat tutors forget everything between sessions. A student re-explains context every time; the tutor never learns *about the student* (what they struggle with, what they've mastered).
- **Solution — persistent memory graph:** Cognee turns uploaded course notes into a knowledge graph (concepts + relationships) that persists on disk. On top of it, MemoryTutor tracks per-topic learner state (`WeakArea` / `MasteredTopic`) so each new session starts with "Last session you struggled with X — want to revisit it?"

## 2. Environment (already confirmed on this machine)

- Windows 11, Python 3.12.10 — compatible with cognee 1.2.2 (`>=3.10,<3.15`, Windows explicitly supported) **[verified]**
- Empty git repo at project root.

## 3. Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| Memory engine | `cognee` (pin `~=1.2`) | add / cognify / search; bundled file-based DBs, no servers needed **[verified]** |
| LLM | Gemini via LiteLLM (built into cognee) | `LLM_PROVIDER=gemini`, `LLM_MODEL=gemini/gemini-1.5-flash` **[verified format]** |
| Embeddings | `gemini/text-embedding-004` (768 dims) | `EMBEDDING_PROVIDER=gemini` **[verified format]** |
| UI | `streamlit` | sidebar + chat + graph panel |
| Graph viz | `networkx` + `matplotlib` | built from cognee's graph engine data |
| PDF text | `pypdf` | fallback extraction; cognee also ingests files directly |
| Config | `python-dotenv` | load `.env` |

⚠️ **Gemini 1.5 retirement risk:** Google has been retiring `gemini-1.5-*` for new API projects. Honor the requested default in `.env.example`, but the model name MUST be read from env so the user can switch to `gemini/gemini-2.0-flash` (the model cognee's own docs now use) if `gemini-1.5-flash` returns a 404/deprecated error. Note this in README troubleshooting.

## 4. Cognee facts to build against **[verified]**

```python
import cognee
from cognee import SearchType

await cognee.add(file_path_or_text, dataset_name="course_notes")   # ingest
await cognee.cognify(datasets=["course_notes"])                     # build graph
answer = await cognee.search(
    query_text=question,
    query_type=SearchType.GRAPH_COMPLETION,   # graph-aware QA, not plain vector search
    datasets=["course_notes"],
)
```

- **All cognee calls are async** → Streamlit needs a `run_async()` helper (§7).
- Default storage is file-based under `.cognee_system/` (SQLite relational, LanceDB vector, Kuzu-compatible graph store) — this is what makes memory *persist across sessions* with zero infra. Add `.cognee_system/` and `.data_storage/` (default data dir) to `.gitignore`.
- Raw graph access for visualization:

```python
from cognee.infrastructure.databases.graph import get_graph_engine
graph_engine = await get_graph_engine()
nodes, edges = await graph_engine.get_graph_data()      # async
metrics = await graph_engine.get_graph_metrics()        # {'num_nodes': .., 'num_edges': ..}
```

- Other useful search types exist (`GRAPH_COMPLETION_COT`, `CHUNKS`); we only need `GRAPH_COMPLETION`.

## 5. Repository layout

```
MemoryTutor/
├── app.py                  # Streamlit entry point (UI only, thin)
├── memory_tutor/
│   ├── __init__.py
│   ├── config.py           # load .env, set cognee env vars BEFORE importing cognee elsewhere
│   ├── engine.py           # async cognee ops: ingest(), ask(), get_graph()
│   ├── tracker.py          # WeakArea/MasteredTopic logic + persistence
│   └── viz.py              # networkx/matplotlib figure builder
├── scripts/
│   └── smoke_test.py       # CLI: add sample text → cognify → search; run BEFORE building UI
├── sample_data/
│   └── sample_notes.txt    # small CS/ML notes file for demo
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── DEMO.md
└── PLAN.md                 # this file
```

## 6. Component specs

### 6.1 `config.py`
- `load_dotenv()` at import; read `GEMINI_API_KEY` and export the vars cognee/LiteLLM read:
  ```
  LLM_PROVIDER=gemini
  LLM_MODEL=gemini/gemini-1.5-flash        # overridable via env
  LLM_API_KEY=$GEMINI_API_KEY
  EMBEDDING_PROVIDER=gemini
  EMBEDDING_MODEL=gemini/text-embedding-004
  EMBEDDING_API_KEY=$GEMINI_API_KEY
  EMBEDDING_DIMENSIONS=768
  ```
- Set these with `os.environ.setdefault(...)` **before any `import cognee`** (cognee reads env at import/first use). Every other module imports `config` first.
- Fail fast with a clear Streamlit error if `GEMINI_API_KEY` is missing.

### 6.2 `engine.py` — cognee wrapper
- `run_async(coro)`: run coroutine from Streamlit's sync context. Use `asyncio.new_event_loop()` per call (or a module-level persistent loop in a dedicated thread — prefer the persistent-loop-in-thread pattern; naive `asyncio.run()` per Streamlit rerun can break cognee's cached DB connections **[verify at impl time]**). On Windows, set `asyncio.WindowsSelectorEventLoopPolicy` if Proactor-loop errors appear.
- `ingest_file(path) -> None`: `cognee.add(path, dataset_name="course_notes")` then `cognee.cognify(datasets=["course_notes"])`. For uploaded files, write the Streamlit `UploadedFile` bytes to a local `uploads/` dir first — cognee.add takes file paths/text. PDFs: pass the file path (cognee handles PDF ingestion natively **[verify at impl time]**; fallback = extract text with `pypdf` and add as text).
- `ask(question) -> str`: `cognee.search(query_text=..., query_type=SearchType.GRAPH_COMPLETION, datasets=["course_notes"])`; normalize the return (list of strings/dicts) to a single answer string.
- `get_graph() -> (nodes, edges)`: via `get_graph_engine()` as in §4.

### 6.3 `tracker.py` — learner-state memory (WeakArea / MasteredTopic)

**Design decision — dual-write:** cognee's custom-node API (`DataPoint` subclasses + `add_data_points`) exists but is low-level and version-sensitive **[verify at impl time]**. To keep session-start retrieval fast and deterministic, use:

1. **Authoritative store:** `user_memory.json` (or SQLite) in project root:
   ```json
   {"topics": {"backpropagation": {"status": "weak", "questions": 3, "followups": 2,
     "last_seen": "2026-07-02T18:30:00", "sessions": ["<uuid>", ...]}}}
   ```
2. **Graph mirror:** after each session update, `cognee.add()` a structured natural-language memory statement into a **separate dataset** `"user_memory"` (e.g. `"WeakArea: The student struggled with backpropagation, asking 2 follow-up clarifications on 2026-07-02."`) and `cognify` it. This puts WeakArea/MasteredTopic nodes into the same graph the tutor searches, so `GRAPH_COMPLETION` answers can reference the student's history ("as you found tricky last time…"), and they show up in the visualization.
   - *Stretch (only if trivial in installed version):* use `DataPoint` subclasses `WeakArea(topic, followup_count, last_seen)` / `MasteredTopic(topic, last_seen)` via `cognee.low_level` instead of text statements.

**Classification heuristic (deterministic, no extra LLM cost):**
- **Topic extraction:** one cheap Gemini call per user question via LiteLLM (`litellm.completion`) with prompt "name the single course topic of this question in ≤4 words"; lowercase-normalize. (LiteLLM is already a cognee dependency — no new package.)
- **Follow-up detection:** a question is a follow-up if (a) same extracted topic as any of the last 3 turns, or (b) starts with clarification phrasing ("what do you mean", "explain again", "i don't get", "why", "can you simplify"). Also render an explicit **"Still confused 🤔" / "Got it ✅"** button pair under each answer — button clicks are the strongest signal and make the demo reliable.
- **Rules:** ≥1 follow-up or "Still confused" click → topic becomes/stays `WeakArea`. "Got it" click, or a session where the topic is asked once with no follow-up **and** it was previously weak → promote to `MasteredTopic`.

- API: `record_interaction(topic, was_followup)`, `mark_confused(topic)`, `mark_mastered(topic)`, `get_weak_areas() -> list[dict]`, `end_session_flush()` (writes graph mirror).

### 6.4 `viz.py` — concept graph panel
- Input: `(nodes, edges)` from `engine.get_graph()`. Build `networkx.DiGraph`; node label = entity `name` attribute (fallback: truncated id); edge label = `relationship_name` **[verify exact attribute keys at impl time by printing one node/edge]**.
- Filter to keep it readable: drop chunk/document infrastructure nodes (keep types like `Entity`, `EntityType`, and the WeakArea/Mastered statement entities); cap at ~60 highest-degree nodes.
- Draw with `nx.spring_layout(seed=42)` + `matplotlib`; color WeakArea-related nodes red, mastered green, concepts default blue. Return the `Figure`; `app.py` renders with `st.pyplot(fig)`.
- Cache with `st.cache_data(ttl=...)` keyed on a "graph version" counter bumped after each cognify, so it doesn't refetch on every rerun.

### 6.5 `app.py` — Streamlit UI
- `st.set_page_config(layout="wide")`; `st.session_state` keys: `messages`, `session_id` (uuid), `recent_topics`, `graph_version`, `greeted`.
- **Sidebar (left panel):**
  - `st.file_uploader(accept_multiple_files=True, type=["pdf","txt","md"])` + "Process notes" button → save to `uploads/`, `ingest_file()` with `st.spinner` + `st.toast` on completion; bump `graph_version`.
  - **"Your weak areas"** section: `tracker.get_weak_areas()` rendered as buttons; clicking one injects "Let's revisit <topic>" into the chat.
- **Session-start banner:** on first run of a session (`greeted` unset), if weak areas exist show `st.info("Last session you struggled with X — want to revisit it?")` with a "Yes, revisit" button.
- **Main column — chat:** `st.chat_message` history + `st.chat_input`. On each question: extract topic → detect follow-up → `tracker.record_interaction` → `engine.ask()` with spinner → render answer + the Still-confused/Got-it buttons.
- **Below chat — graph:** expander "🕸 Concept graph" with the matplotlib figure + node/edge counts from `get_graph_metrics()`; empty-state message before first upload.
- Flush tracker to the graph mirror after each classification change (Streamlit has no reliable session-end hook — don't defer writes to "session end").

## 7. Deliverable files

**`requirements.txt`** (pin majors only):
```
cognee~=1.2
streamlit>=1.35
networkx>=3.0
matplotlib>=3.8
pypdf>=4.0
python-dotenv>=1.0
```

**`.env.example`**:
```
GEMINI_API_KEY=your-google-ai-studio-key-here
# Optional overrides (defaults shown)
LLM_MODEL=gemini/gemini-1.5-flash
EMBEDDING_MODEL=gemini/text-embedding-004
```

**`.gitignore`**: `.env`, `.cognee_system/`, `.data_storage/`, `uploads/`, `user_memory.json`, `__pycache__/`, `.venv/`

**`README.md`** sections: The problem (AI amnesia) → The solution (persistent memory graph — explain add/cognify/search pipeline and the WeakArea/MasteredTopic layer) → Architecture diagram (ASCII) → Setup (venv, pip install, copy `.env.example`→`.env`, get key at aistudio.google.com) → Run (`streamlit run app.py`) → How memory works across sessions → Troubleshooting (Gemini 1.5 retirement → switch model; first cognify is slow; Windows event-loop note).

**`DEMO.md`** — 3-minute script:
1. *(0:00–0:30)* Hook: "Every AI tutor has amnesia." Show empty app, upload `sample_notes.txt`, click Process — narrate that Cognee is building a knowledge graph, show the graph appear below the chat.
2. *(0:30–1:30)* Ask a question ("Explain backpropagation"), get a graph-grounded answer. Ask a follow-up ("I still don't get the chain rule part"), click **Still confused** — point out "Weak areas" updating in the sidebar.
3. *(1:30–2:20)* **The money shot:** stop the app (`Ctrl+C`), restart `streamlit run app.py` — new session greets with "Last session you struggled with backpropagation — want to revisit it?" Click revisit, get a tailored re-explanation, click **Got it** → topic turns green/mastered.
4. *(2:20–3:00)* Show the concept graph (weak nodes in red), close on the pitch: memory graph persists on disk, no external DB, works with any course notes.

## 8. Implementation order (milestones)

1. **M1 — Pipeline proof:** `config.py` + `engine.py` + `scripts/smoke_test.py`. Run the smoke test with a real key: add sample text → cognify → GRAPH_COMPLETION search → print graph metrics. **Do not start the UI until this passes** — it derisks the Gemini/LiteLLM config, model retirement, and async issues in one shot. Print one raw node/edge here to pin down attribute keys for viz.
2. **M2 — Tracker:** `tracker.py` with JSON store + unit-testable classification rules; graph-mirror write.
3. **M3 — UI:** `app.py` chat + upload + weak-area sidebar + session-start banner.
4. **M4 — Graph viz:** `viz.py` + panel below chat.
5. **M5 — Docs & polish:** README, DEMO, `.env.example`, sample notes; run the DEMO.md script end-to-end once as acceptance.

## 9. Acceptance criteria

- [ ] Fresh clone + `.env` + `pip install -r requirements.txt` + `streamlit run app.py` works on Windows/Python 3.12.
- [ ] Uploading a PDF or txt produces a non-empty graph (metrics > 0) and answers cite note content.
- [ ] Answers use `SearchType.GRAPH_COMPLETION` (grep-verifiable).
- [ ] Asking a follow-up (or clicking Still confused) creates a WeakArea visible in the sidebar **and** as a node in the graph dataset.
- [ ] Restarting the app surfaces "Last session you struggled with X…" without re-uploading anything.
- [ ] Graph panel renders, readable, with weak topics highlighted.

## 10. Known risks & mitigations

| Risk | Mitigation |
|---|---|
| `gemini-1.5-flash` retired by Google | Model name env-configurable; README troubleshooting entry; test in M1 |
| Cognee async vs Streamlit reruns | Persistent event loop in background thread; M1 smoke test exercises repeated calls |
| Cognee API drift (custom DataPoints, node attribute names) | Dual-write design avoids depending on low-level APIs; M1 prints raw graph data |
| First `cognify()` latency (minutes on big PDFs) | Spinner + toast; demo uses small `sample_notes.txt`; note in README |
| Gemini free-tier rate limits (esp. embeddings) | Small sample data; catch 429s and show a friendly retry message |
| Graph too dense to read | Node-type filter + top-60-by-degree cap in `viz.py` |
