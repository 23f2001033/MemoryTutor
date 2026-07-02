# MemoryTutor

An AI study tutor that remembers what you struggle with — across sessions.

**🔗 Live demo: [memorytutor-8xubbwgxarbmzutwjeger2.streamlit.app](https://memorytutor-8xubbwgxarbmzutwjeger2.streamlit.app/)**

## The problem: AI amnesia

Every chat-based tutor has the same flaw: it forgets you the moment the conversation ends. Ask it to explain backpropagation today, ask again next week, and it starts from zero — no memory of what confused you, what you've already mastered, or what your notes even said. You end up re-explaining your own context to the AI every single session. The tutor never actually gets to know you as a learner.

## The solution: a persistent memory graph

MemoryTutor is built on [Cognee](https://www.cognee.ai/), which turns your course notes into a **knowledge graph** — concepts as nodes, relationships between them as edges — stored on disk instead of in a chat window that disappears when you close the tab.

On top of that graph, MemoryTutor tracks a second layer of memory: **what you personally struggle with**. Every question you ask, every follow-up clarification you need, feeds into a `WeakArea` / `MasteredTopic` model for each topic. That model is:

1. **Stored locally** in `user_memory.json`, so lookups at the start of a session are instant.
2. **Mirrored into the same knowledge graph** as short memory statements (e.g. *"WeakArea: gradient descent is a topic the learner finds difficult..."*), so the tutor's answers can reference your history and the concept graph visualization can highlight what you're struggling with.

The result: close the app, come back tomorrow, and MemoryTutor greets you with *"Last session you struggled with gradient descent — want to revisit it?"* — because it actually remembers.

## Architecture

```
┌─────────────────────────┐
│   Streamlit UI (app.py) │
│  ┌────────────┐ ┌──────┐│
│  │  Sidebar   │ │ Chat ││
│  │ (uploads,  │ │      ││
│  │ weak areas)│ │      ││
│  └────────────┘ └──────┘│
│  ┌──────────────────────┐│
│  │  Concept graph panel ││
│  └──────────────────────┘│
└───────────┬──────────────┘
            │
   ┌────────┴─────────┐
   │                   │
┌──▼───────┐    ┌──────▼───────┐
│engine.py │    │  tracker.py  │
│(cognee   │    │(WeakArea /   │
│ add/     │◄───┤ MasteredTopic│
│ cognify/ │    │  JSON store  │
│ search)  │    │  + graph     │
└──┬───────┘    │  mirroring)  │
   │            └──────────────┘
┌──▼─────────────────────────┐
│  Cognee (LiteLLM + Gemini) │
│  knowledge graph, stored   │
│  in .cognee_system/ and    │
│  .data_storage/            │
└─────────────────────────────┘
```

- **`engine.py`** — thin async wrapper around `cognee.add()`, `cognee.cognify()`, and `cognee.search(..., SearchType.GRAPH_COMPLETION)`. All cognee calls are async; a persistent background event loop bridges them into Streamlit's synchronous script model.
- **`tracker.py`** — the learner-state layer: extracts a topic per question (via a cheap Gemini call), detects follow-ups (keyword heuristics + explicit "Still confused" / "Got it" buttons), and maintains WeakArea/MasteredTopic status both locally and in the graph.
- **`viz.py`** — builds a `networkx` graph from cognee's raw graph data and renders it with `matplotlib`, filtering out cognee's internal bookkeeping nodes (chunks, summaries) so only real course concepts show up, colored red (weak) / green (mastered) / blue (neutral).
- **`app.py`** — the Streamlit UI tying it together.

## Setup

1. **Get a Gemini API key** at [aistudio.google.com/apikey](https://aistudio.google.com/apikey).

2. **Create a virtual environment and install dependencies:**

   ```bash
   python -m venv .venv
   .venv\Scripts\activate          # Windows
   # source .venv/bin/activate     # macOS/Linux
   pip install -r requirements.txt
   ```

3. **Configure your API key:**

   ```bash
   copy .env.example .env          # Windows
   # cp .env.example .env          # macOS/Linux
   ```

   Then edit `.env` and set `GEMINI_API_KEY`.

## Running it

```bash
streamlit run app.py
```

Open the URL Streamlit prints (usually `http://localhost:8501`), upload a PDF or text file of course notes from the sidebar, click **Process notes**, and start asking questions.

> **Don't run other cognee scripts (like `scripts/smoke_test.py`) while the app is running.** Cognee's graph database uses file locking and doesn't support concurrent access from multiple processes — stop the Streamlit app first.

## Deploying to Streamlit Community Cloud

**Live demo: [memorytutor-8xubbwgxarbmzutwjeger2.streamlit.app](https://memorytutor-8xubbwgxarbmzutwjeger2.streamlit.app/)**

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
2. **New app** → pick this repo, branch `main`, main file path `app.py`.
3. Before clicking Deploy, open **Advanced settings → Secrets** and paste:
   ```toml
   GEMINI_API_KEY = "your-key-here"
   ```
   (`LLM_MODEL` / `EMBEDDING_MODEL` overrides are optional, same as `.env.example`.)
4. Click **Deploy**.

Two things behave differently on Streamlit Cloud versus running locally:

- **Storage is ephemeral.** Streamlit Cloud doesn't guarantee a persistent disk across app restarts/redeploys, so the knowledge graph and weak-area memory may reset when the app sleeps from inactivity and wakes back up. Cross-session memory is fully persistent when you run the app locally (that's what `DEMO.md` demonstrates); on the free cloud tier, treat it as persistent within a single "awake" period rather than indefinitely.
- **Memory footprint.** Cognee's local graph/vector stores plus its dependency stack are heavier than a typical Streamlit app. If the free tier's ~1GB RAM limit causes crashes, that's a platform constraint, not an app bug.

## How memory works across sessions

1. **Upload notes** → `cognee.add()` ingests the file, `cognee.cognify()` extracts entities and relationships into a knowledge graph, stored in `.cognee_system/` and `.data_storage/` in this project directory (not inside the venv, so it survives `pip install` reruns).
2. **Ask a question** → MemoryTutor extracts the topic, checks whether it's a follow-up (either by phrasing like *"I don't get it"* or because you asked about the same topic recently), and answers using `cognee.search(query_type=SearchType.GRAPH_COMPLETION)` — a graph-aware retrieval that reasons over entity relationships, not just vector similarity.
3. **Struggle or succeed** → each follow-up (or an explicit "Still confused" click) marks the topic as a `WeakArea`; clicking "Got it" marks it `MasteredTopic`. Both are saved to `user_memory.json` and mirrored into the graph.
4. **Come back later** → on a fresh session, MemoryTutor reads your weak areas and greets you with a prompt to revisit them — no re-uploading, no re-explaining.

## Project layout

```
MemoryTutor/
├── app.py                  # Streamlit UI
├── memory_tutor/
│   ├── config.py           # .env loading, Gemini/LiteLLM env wiring
│   ├── engine.py           # async cognee wrapper
│   ├── tracker.py          # WeakArea/MasteredTopic tracking
│   └── viz.py              # networkx + matplotlib concept graph
├── scripts/
│   └── smoke_test.py       # CLI pipeline check (add → cognify → search)
├── sample_data/
│   └── sample_notes.txt    # sample notes for a quick demo
├── requirements.txt
├── .env.example
└── DEMO.md
```

## Troubleshooting

- **`gemini-1.5-flash` / `text-embedding-004` not found (404).** Google has retired these models. MemoryTutor defaults to `gemini/gemini-flash-lite-latest` (chat/topic extraction) and `gemini/gemini-embedding-001` (embeddings) instead — both current and free-tier friendly. If you have a paid key, set `LLM_MODEL=gemini/gemini-2.5-flash` in `.env` for noticeably better answer quality.
- **Rate limit / 429 errors.** Free-tier Gemini keys have low daily quotas per model (as low as ~20 requests/day for `gemini-2.5-flash`). Cognee retries automatically with backoff, so slow responses during heavy use are expected; if it hard-fails, wait a bit or switch to a lite model.
- **First `cognify()` on a new file is slow.** Entity/relationship extraction runs an LLM call per text chunk. The bundled `sample_data/sample_notes.txt` is small and ingests in well under a minute; large PDFs will take longer.
- **"Could not set lock on file" error.** Cognee's graph database doesn't support concurrent multi-process access. Make sure only one process (the Streamlit app *or* a CLI script, not both) is touching `.cognee_system/` at a time.
- **Storage location.** By default cognee stores its databases inside its own package folder, which would delete your "persistent" memory every time you reinstall dependencies. MemoryTutor overrides this in `config.py` to store everything under the project root instead (`.cognee_system/`, `.data_storage/`), so it survives `pip install` reruns — just don't delete those folders if you want to keep your memory.
