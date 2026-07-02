"""Pipeline proof: add sample text -> cognify -> GRAPH_COMPLETION search -> print graph metrics.

Run this before touching the Streamlit UI:

    python scripts/smoke_test.py

It exercises the real Gemini API (LLM + embeddings), so it needs a valid
GEMINI_API_KEY in .env. It also prints one raw node/edge so viz.py can be
built against the real attribute names cognee returns.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from memory_tutor import config, engine  # noqa: E402


def main():
    sample_path = os.path.join(config.PROJECT_ROOT, "sample_data", "sample_notes.txt")

    print(f"[1/4] Ingesting {sample_path} into dataset '{config.NOTES_DATASET}' ...")
    engine.ingest_file(sample_path, config.NOTES_DATASET)
    print("      done.")

    print("[2/4] Asking a GRAPH_COMPLETION question ...")
    answer = engine.ask("Explain backpropagation and how it relates to the chain rule.")
    print(f"      Answer: {answer}\n")

    print("[3/4] Fetching graph metrics ...")
    metrics = engine.get_graph_metrics()
    print(f"      Metrics: {metrics}")

    print("[4/4] Fetching one raw node and edge to inspect attribute names ...")
    nodes, edges = engine.get_graph()
    print(f"      Total nodes: {len(nodes)}, total edges: {len(edges)}")
    if nodes:
        sample_node = nodes[0]
        print(f"      Sample node type: {type(sample_node)}")
        print(f"      Sample node repr: {sample_node!r}")
    if edges:
        sample_edge = edges[0]
        print(f"      Sample edge type: {type(sample_edge)}")
        print(f"      Sample edge repr: {sample_edge!r}")

    print("\nSmoke test complete.")


if __name__ == "__main__":
    main()
