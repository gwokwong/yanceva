"""Graphiti + Neo4j backed graph store.

Replaces the retired Zep Cloud integration. ``graph_id`` maps 1:1 to a
Graphiti ``group_id`` namespace inside a single Neo4j database, so the
durable ``mirofish_<hex16>`` ids produced by MiroFish keep working.
"""

from __future__ import annotations

import threading
from typing import Optional

from .base import GraphStore

_store: Optional[GraphStore] = None
_store_lock = threading.Lock()


def get_graph_store() -> GraphStore:
    """Return the process-shared graph store instance (Graphiti-backed)."""

    global _store
    if _store is not None:
        return _store

    with _store_lock:
        if _store is not None:
            return _store
        # Imported lazily so importing this package does not pull in the
        # heavy graphiti stack (used by lightweight API routes too).
        from .graphiti_store import GraphitiStore

        _store = GraphitiStore()
        return _store


def reset_graph_store() -> None:
    """Drop the cached store instance. Intended for tests."""

    global _store
    with _store_lock:
        _store = None


__all__ = ["GraphStore", "get_graph_store", "reset_graph_store"]
