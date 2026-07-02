"""MemoryTutor — an AI study tutor with a persistent, cross-session memory graph."""
import os
import uuid

import streamlit as st

st.set_page_config(page_title="MemoryTutor", layout="wide")

try:
    from memory_tutor import config
except RuntimeError as exc:
    st.error(str(exc))
    st.stop()

from memory_tutor import engine, tracker, viz

FOLLOWUP_WINDOW = 3
RECENT_TOPICS_KEPT = 5


def init_session_state():
    defaults = {
        "messages": [],
        "session_id": str(uuid.uuid4()),
        "recent_topics": [],
        "graph_version": 0,
        "greeted": False,
        "pending_prompt": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def save_uploaded_file(uploaded_file) -> str:
    path = os.path.join(config.UPLOADS_DIR, uploaded_file.name)
    with open(path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return path


def handle_question(question: str):
    topic = tracker.extract_topic(question)
    is_followup = tracker.looks_like_followup(question) or topic in st.session_state.recent_topics[-FOLLOWUP_WINDOW:]

    tracker.record_interaction(topic, is_followup)
    st.session_state.recent_topics.append(topic)
    st.session_state.recent_topics = st.session_state.recent_topics[-RECENT_TOPICS_KEPT:]

    st.session_state.messages.append({"role": "user", "content": question})
    with st.spinner("Thinking through your notes..."):
        try:
            answer = engine.ask(question)
        except Exception as exc:
            answer = f"Something went wrong answering that: {exc}"
    st.session_state.messages.append({"role": "assistant", "content": answer, "topic": topic})


def render_message(i, msg):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and "topic" in msg:
            col1, col2 = st.columns([1, 1])
            with col1:
                if st.button("😕 Still confused", key=f"confused_{i}"):
                    tracker.mark_confused(msg["topic"])
                    st.rerun()
            with col2:
                if st.button("✅ Got it", key=f"mastered_{i}"):
                    tracker.mark_mastered(msg["topic"])
                    st.rerun()


init_session_state()

# st.chat_input always pins itself to the bottom of the page no matter where
# in the script it's called, so we read and process it here, before the
# sidebar/banner render below — that way a question asked this run (and any
# resulting weak-area/mastered change) is immediately reflected in the same
# run instead of lagging a step behind.
question = st.chat_input("Ask a question about your course notes...")
if st.session_state.pending_prompt:
    question = st.session_state.pending_prompt
    st.session_state.pending_prompt = None

if question:
    handle_question(question)

st.title("🧠 MemoryTutor")
st.caption("An AI study tutor that remembers what you struggle with — across sessions.")

# ---------------------------------------------------------------- Sidebar --
with st.sidebar:
    st.header("📄 Course notes")
    uploaded_files = st.file_uploader(
        "Upload PDF or text notes",
        type=["pdf", "txt", "md"],
        accept_multiple_files=True,
    )
    if st.button("Process notes", disabled=not uploaded_files):
        for uploaded_file in uploaded_files:
            path = save_uploaded_file(uploaded_file)
            with st.spinner(f"Building knowledge graph from {uploaded_file.name}..."):
                try:
                    engine.ingest_file(path)
                    st.toast(f"Added {uploaded_file.name} to your memory graph.")
                except Exception as exc:
                    st.error(f"Failed to process {uploaded_file.name}: {exc}")
        st.session_state.graph_version += 1

    st.divider()
    st.header("🎯 Your weak areas")
    weak_areas = tracker.get_weak_areas()
    if not weak_areas:
        st.caption("No weak areas tracked yet — ask some questions to get started.")
    else:
        for area in sorted(weak_areas, key=lambda a: a["last_seen"] or "", reverse=True):
            label = f"🔴 {area['topic']} ({area['followups']} follow-up(s))"
            if st.button(label, key=f"weak_{area['topic']}", use_container_width=True):
                st.session_state.pending_prompt = f"Let's revisit {area['topic']}. Can you re-explain it?"
                st.rerun()

    mastered = tracker.get_mastered_topics()
    if mastered:
        st.divider()
        st.header("✅ Mastered")
        for m in mastered:
            st.caption(f"🟢 {m['topic']}")

# ------------------------------------------------------- Session banner ---
if not st.session_state.greeted:
    st.session_state.greeted = True
    if weak_areas:
        top = sorted(weak_areas, key=lambda a: a["last_seen"] or "", reverse=True)[0]
        st.info(f"👋 Last session you struggled with **{top['topic']}** — want to revisit it?")
        if st.button("Yes, revisit it"):
            st.session_state.pending_prompt = f"Let's revisit {top['topic']}. Can you re-explain it?"
            st.rerun()

# ------------------------------------------------------------- Chat UI ----
st.subheader("💬 Chat with your tutor")

for i, msg in enumerate(st.session_state.messages):
    render_message(i, msg)

# ---------------------------------------------------------- Graph panel ---
st.divider()
with st.expander("🕸️ Concept graph", expanded=False):
    try:
        nodes, edges = engine.get_graph()
    except Exception as exc:
        nodes, edges = [], []
        st.error(f"Could not load the graph: {exc}")

    if not nodes:
        st.caption("Upload some notes to see your concept graph here.")
    else:
        metrics = engine.get_graph_metrics()
        st.caption(f"{metrics.get('num_nodes', 0)} nodes, {metrics.get('num_edges', 0)} edges")
        fig = viz.render_graph(nodes, edges)
        if fig is not None:
            st.pyplot(fig)
        else:
            st.caption("No concept nodes to display yet.")
