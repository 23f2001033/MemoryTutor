"""Builds a networkx concept graph from cognee's raw graph data and renders it
with matplotlib for the Streamlit panel below the chat.
"""
import re

import networkx as nx
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from memory_tutor import tracker

# cognee tags every graph node with a `type`; only these represent actual
# course concepts. Everything else (DocumentChunk, TextDocument, TextSummary,
# EntityType) is graph-building infrastructure we don't want cluttering the
# panel.
CONCEPT_NODE_TYPES = {"Entity"}

MAX_NODES = 60

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_GENERIC_LABELS = {"student", "a student", "the student", "learner", "topic", "count", "date"}


def _is_real_concept(label: str) -> bool:
    """Filters out incidental entities (dates, bare numbers, generic pronouns)
    that cognee's extractor pulls out of memory-tracking sentences but that
    aren't course concepts worth showing on the graph."""
    normalized = label.strip().lower()
    if not normalized or normalized in _GENERIC_LABELS:
        return False
    if _DATE_RE.match(normalized) or normalized.isdigit():
        return False
    return True


def build_networkx_graph(nodes, edges) -> nx.DiGraph:
    """nodes: list of (id, attrs). edges: list of (source_id, target_id, relation, attrs)."""
    graph = nx.DiGraph()

    concept_ids = {
        node_id
        for node_id, attrs in nodes
        if attrs.get("type") in CONCEPT_NODE_TYPES and _is_real_concept(attrs.get("name") or "")
    }
    labels = {
        node_id: attrs.get("name") or node_id[:8]
        for node_id, attrs in nodes
        if node_id in concept_ids
    }

    for node_id in concept_ids:
        graph.add_node(node_id, label=labels[node_id])

    for source, target, relation, _attrs in edges:
        if source in concept_ids and target in concept_ids:
            graph.add_edge(source, target, label=relation)

    if graph.number_of_nodes() > MAX_NODES:
        top_nodes = sorted(graph.degree, key=lambda x: x[1], reverse=True)[:MAX_NODES]
        graph = graph.subgraph([n for n, _ in top_nodes]).copy()

    return graph


def _node_color(label: str, weak_topics: set, mastered_topics: set) -> str:
    normalized = tracker.normalize_topic(label)
    if any(normalized in weak or weak in normalized for weak in weak_topics):
        return "#e05252"  # red — weak area
    if any(normalized in mastered or mastered in normalized for mastered in mastered_topics):
        return "#4caf7d"  # green — mastered
    return "#5b8def"  # blue — neutral concept


def render_graph(nodes, edges):
    """Returns a matplotlib Figure showing the concept graph, or None if empty."""
    graph = build_networkx_graph(nodes, edges)
    if graph.number_of_nodes() == 0:
        return None

    weak_topics = {tracker.normalize_topic(w["topic"]) for w in tracker.get_weak_areas()}
    mastered_topics = {tracker.normalize_topic(m["topic"]) for m in tracker.get_mastered_topics()}

    labels = nx.get_node_attributes(graph, "label")
    colors = [_node_color(labels[n], weak_topics, mastered_topics) for n in graph.nodes]

    fig, ax = plt.subplots(figsize=(11, 7))
    pos = nx.spring_layout(graph, seed=42, k=0.6)

    nx.draw_networkx_nodes(graph, pos, node_color=colors, node_size=600, alpha=0.9, ax=ax)
    nx.draw_networkx_edges(
        graph, pos, alpha=0.35, arrows=True, arrowsize=10, width=1.0, ax=ax
    )
    nx.draw_networkx_labels(graph, pos, labels=labels, font_size=8, ax=ax)

    ax.set_axis_off()
    fig.tight_layout()
    return fig
