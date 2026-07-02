"""Async cognee wrapper: ingest notes, ask questions, read the graph.

All cognee operations are async. Streamlit runs synchronously, so we drive a
single persistent event loop on a background thread and submit coroutines to
it via run_async(). Reusing one loop (instead of asyncio.run() per call)
avoids repeatedly tearing down cognee's cached DB connections across
Streamlit reruns.
"""
import asyncio
import atexit
import os
import threading

from memory_tutor import config  # noqa: F401  (sets env vars before cognee import)

import cognee
from cognee import SearchType
from cognee.infrastructure.databases.graph import get_graph_engine

if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

_loop = asyncio.new_event_loop()
_loop_thread = threading.Thread(target=_loop.run_forever, daemon=True)
_loop_thread.start()


def run_async(coro):
    """Submit a coroutine to the persistent background loop and block for the result."""
    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    return future.result()


@atexit.register
def _shutdown_loop():
    _loop.call_soon_threadsafe(_loop.stop)


async def _ingest_file_async(path: str, dataset_name: str) -> None:
    await cognee.add(path, dataset_name=dataset_name)
    await cognee.cognify(datasets=[dataset_name])


def ingest_file(path: str, dataset_name: str = config.NOTES_DATASET) -> None:
    """Add a file to cognee and build/extend the knowledge graph from it."""
    run_async(_ingest_file_async(path, dataset_name))


async def _ingest_text_async(text: str, dataset_name: str) -> None:
    await cognee.add(text, dataset_name=dataset_name)
    await cognee.cognify(datasets=[dataset_name])


def ingest_text(text: str, dataset_name: str = config.MEMORY_DATASET) -> None:
    """Add a raw text memory statement (e.g. a WeakArea note) and cognify it."""
    run_async(_ingest_text_async(text, dataset_name))


async def _ask_async(question: str, datasets: list) -> str:
    results = await cognee.search(
        query_text=question,
        query_type=SearchType.GRAPH_COMPLETION,
        datasets=datasets,
    )
    if not results:
        return "I don't have any notes to answer that yet — upload some course material first."
    # cognee.search results may be plain strings or SearchResult-like objects
    # exposing `.search_result` (a string or a list containing one), depending
    # on version/search type. Handle both shapes defensively.
    first = results[0]
    payload = getattr(first, "search_result", first)
    if isinstance(payload, str):
        return payload
    if isinstance(payload, list) and payload:
        return payload[0] if isinstance(payload[0], str) else str(payload[0])
    return str(payload)


def ask(question: str, datasets=None) -> str:
    """Answer a question using graph-aware completion over ingested notes + memory."""
    if datasets is None:
        datasets = [config.NOTES_DATASET, config.MEMORY_DATASET]
    return run_async(_ask_async(question, datasets))


async def _get_graph_async():
    graph_engine = await get_graph_engine()
    nodes, edges = await graph_engine.get_graph_data()
    return nodes, edges


def get_graph():
    """Return (nodes, edges) as reported by cognee's graph engine."""
    return run_async(_get_graph_async())


async def _get_graph_metrics_async():
    graph_engine = await get_graph_engine()
    return await graph_engine.get_graph_metrics()


def get_graph_metrics():
    return run_async(_get_graph_metrics_async())


async def _prune_async():
    await cognee.prune.prune_data()
    await cognee.prune.prune_system(metadata=True)


def reset_all():
    """Wipe all cognee-managed storage. Used for smoke testing / full resets only."""
    run_async(_prune_async())
