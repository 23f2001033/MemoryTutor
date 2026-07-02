# MemoryTutor — 3-Minute Demo Script

**Setup before recording:** make sure `.cognee_system/`, `.data_storage/`, and `user_memory.json` are deleted (or just cloned fresh) so the app starts with zero memory — the "before" state is the whole point.

---

### 0:00 – 0:30 — The hook

> "Every AI tutor has the same problem: amnesia. Ask it something today, come back tomorrow, and it doesn't remember a thing about you — what you struggled with, what you already know. MemoryTutor fixes that with a persistent memory graph."

- Show the empty app: no weak areas, empty concept graph.
- Upload `sample_data/sample_notes.txt` from the sidebar, click **Process notes**.
- While it processes: "It's not just storing the text — Cognee is extracting concepts and relationships into a knowledge graph."
- Expand **🕸️ Concept graph** to reveal the extracted nodes (neural network, backpropagation, gradient descent, etc.) and edges.

### 0:30 – 1:30 — Teaching and struggling

- Ask: *"Explain backpropagation and how it relates to the chain rule."*
- Point out the answer is graph-grounded, not just a generic LLM response — it uses `SearchType.GRAPH_COMPLETION`, reasoning over the entity graph, not plain vector search.
- Ask a genuine follow-up: *"I still don't get the chain rule part."*
- Point at the sidebar: **🔴 chain rule** (or whichever topic) now appears under "Your weak areas" — instantly, no page reload needed.
- Optionally click the **😕 Still confused** button under an answer to show the explicit signal path too.

### 1:30 – 2:20 — The money shot: memory across sessions

- Stop the app (`Ctrl+C` in the terminal).
- Restart it: `streamlit run app.py`.
- **The banner appears immediately:** *"👋 Last session you struggled with chain rule — want to revisit it?"*
- Click **Yes, revisit it** — MemoryTutor re-explains the topic, tailored to the fact that you've already been told once and it didn't land.
- Click **✅ Got it** on the new answer — the topic moves from "Your weak areas" to "✅ Mastered" in the sidebar.

### 2:20 – 3:00 — Close

- Expand the concept graph again: the mastered topic is now green, other weak topics (if any) are red.
- Closing line: "No external database, no server to manage — the entire memory graph lives on disk in this project folder. Point it at any course notes and it starts building a study profile that actually persists."

---

## Backup talking points (if something runs slow)

- Free-tier Gemini keys are rate-limited; if an answer takes 10–20 seconds, that's cognee's automatic retry/backoff kicking in, not a bug.
- If you want guaranteed snappy answers for a live demo, use a paid Gemini key and set `LLM_MODEL=gemini/gemini-2.5-flash` in `.env` beforehand.
