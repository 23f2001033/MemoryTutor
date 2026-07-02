"""Learner-state memory: tracks per-topic WeakArea / MasteredTopic status.

Authoritative store is a local JSON file (fast, deterministic session-start
lookups). After each status change we also mirror a natural-language memory
statement into cognee's "user_memory" dataset, so the same facts show up as
nodes in the concept graph and can inform GRAPH_COMPLETION answers.
"""
import json
import os
import re
from datetime import datetime, timezone

from memory_tutor import config, engine

_FOLLOWUP_PHRASES = (
    "what do you mean",
    "explain again",
    "i don't get",
    "i dont get",
    "still don't understand",
    "still dont understand",
    "can you simplify",
    "can you clarify",
    "i'm confused",
    "im confused",
    "why is that",
    "why does that",
    "wait, why",
    "huh",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load() -> dict:
    if not os.path.exists(config.USER_MEMORY_PATH):
        return {"topics": {}}
    with open(config.USER_MEMORY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(state: dict) -> None:
    with open(config.USER_MEMORY_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def normalize_topic(topic: str) -> str:
    topic = topic.strip().lower()
    topic = re.sub(r"[^a-z0-9\s\-]", "", topic)
    topic = re.sub(r"\s+", " ", topic)
    return topic[:60]


def looks_like_followup(question: str) -> bool:
    q = question.strip().lower()
    return any(phrase in q for phrase in _FOLLOWUP_PHRASES)


def extract_topic(question: str) -> str:
    """Best-effort topic extraction via a cheap LiteLLM/Gemini call.

    Falls back to a truncated version of the question if the LLM call fails,
    so a single flaky request never breaks the chat flow.
    """
    try:
        import litellm

        response = litellm.completion(
            model=os.environ["LLM_MODEL"],
            api_key=os.environ["LLM_API_KEY"],
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Name the specific concept or term this question is about — "
                        "the narrowest matching phrase from the question itself, not a "
                        "broad subject category. 4 words or fewer, lowercase, no "
                        "punctuation. Example: question 'What is backpropagation?' -> "
                        "'backpropagation', not 'machine learning'. "
                        f"Question: {question}"
                    ),
                }
            ],
            max_tokens=20,
        )
        topic = response["choices"][0]["message"]["content"]
        return normalize_topic(topic)
    except Exception:
        return normalize_topic(question[:40])


def get_weak_areas() -> list:
    state = _load()
    return [
        {"topic": t, **info}
        for t, info in state["topics"].items()
        if info.get("status") == "weak"
    ]


def get_mastered_topics() -> list:
    state = _load()
    return [
        {"topic": t, **info}
        for t, info in state["topics"].items()
        if info.get("status") == "mastered"
    ]


def _mirror_to_graph(topic: str, status: str, followups: int) -> None:
    # Kept short and free of dates/counts/pronouns: cognee's entity extractor
    # turns every noun phrase into a graph node, so anything beyond the topic
    # name itself (a date, "the student", a number) shows up as junk nodes in
    # the concept graph visualization. Follow-up counts and timestamps stay in
    # the authoritative JSON store instead.
    if status == "weak":
        text = f"WeakArea: {topic} is a topic the learner finds difficult and needs more practice with."
    else:
        text = f"MasteredTopic: {topic} is a topic the learner has demonstrated understanding of."
    try:
        engine.ingest_text(text, dataset_name=config.MEMORY_DATASET)
    except Exception:
        # Graph mirroring is best-effort; the JSON store remains authoritative.
        pass


def record_interaction(topic: str, was_followup: bool) -> str:
    """Update state for a question on `topic`. Returns the resulting status."""
    topic = normalize_topic(topic)
    state = _load()
    entry = state["topics"].setdefault(
        topic,
        {"status": "new", "questions": 0, "followups": 0, "last_seen": None},
    )
    entry["questions"] += 1
    if was_followup:
        entry["followups"] += 1
    entry["last_seen"] = _now_iso()

    if was_followup or entry["followups"] > 0:
        entry["status"] = "weak"
    elif entry["status"] == "new":
        entry["status"] = "seen"

    _save(state)
    if entry["status"] == "weak":
        _mirror_to_graph(topic, "weak", entry["followups"])
    return entry["status"]


def mark_confused(topic: str) -> None:
    topic = normalize_topic(topic)
    state = _load()
    entry = state["topics"].setdefault(
        topic,
        {"status": "new", "questions": 0, "followups": 0, "last_seen": None},
    )
    entry["followups"] += 1
    entry["status"] = "weak"
    entry["last_seen"] = _now_iso()
    _save(state)
    _mirror_to_graph(topic, "weak", entry["followups"])


def mark_mastered(topic: str) -> None:
    topic = normalize_topic(topic)
    state = _load()
    entry = state["topics"].setdefault(
        topic,
        {"status": "new", "questions": 0, "followups": 0, "last_seen": None},
    )
    entry["status"] = "mastered"
    entry["last_seen"] = _now_iso()
    _save(state)
    _mirror_to_graph(topic, "mastered", entry["followups"])
