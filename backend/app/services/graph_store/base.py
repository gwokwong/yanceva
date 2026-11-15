"""Graph store abstractions shared by all graph backends.

The MiroFish pipeline (graph build → entity read → persona generation →
simulation memory → report tools) talks to a knowledge-graph backend
through this module only.  The concrete implementation shipped with
MiroFish is :class:`~app.services.graph_store.graphiti_store.GraphitiStore`
backed by graphiti-core + Neo4j, replacing the retired Zep Cloud
integration while keeping the same behavioural contract.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class GraphEdgeResult:
    """A relationship (fact) returned from search or enumeration."""

    uuid: str
    name: str = ""
    fact: str = ""
    source_node_uuid: str = ""
    target_node_uuid: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[str] = None
    valid_at: Optional[str] = None
    invalid_at: Optional[str] = None
    expired_at: Optional[str] = None
    episodes: List[str] = field(default_factory=list)


@dataclass
class GraphNodeResult:
    """An entity returned from search or enumeration."""

    uuid: str
    name: str = ""
    labels: List[str] = field(default_factory=list)
    summary: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[str] = None


@dataclass
class SearchResult:
    """Hybrid-search results scoped to one graph."""

    edges: List[GraphEdgeResult] = field(default_factory=list)
    nodes: List[GraphNodeResult] = field(default_factory=list)


@dataclass
class IngestionResult:
    """Outcome of a document-chunk ingestion run."""

    episode_uuids: List[str] = field(default_factory=list)
    item_count: int = 0
    operation_id: str = ""


ProgressCallback = Callable[[str, float], None]
BatchCreatedCallback = Callable[[Optional[str], str], None]


class GraphStoreError(RuntimeError):
    """Base error for graph store operations."""


class GraphStore(ABC):
    """Backend-neutral synchronous facade over an async graph engine."""

    @abstractmethod
    def create_graph(
        self,
        name: str,
        *,
        graph_id: Optional[str] = None,
        graph_id_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Create a logical graph namespace and return its durable id."""

    @abstractmethod
    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]) -> None:
        """Attach entity/edge type definitions used during ingestion."""

    @abstractmethod
    def add_text_batches(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 350,
        progress_callback: Optional[ProgressCallback] = None,
        batch_created_callback: Optional[BatchCreatedCallback] = None,
    ) -> IngestionResult:
        """Ingest text chunks as episodes and wait until processing finishes."""

    @abstractmethod
    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        """Return full graph payload: nodes, edges and counts."""

    @abstractmethod
    def search(
        self,
        graph_id: str,
        query: str,
        limit: int = 10,
        scope: str = "edges",
    ) -> SearchResult:
        """Hybrid semantic search; ``scope`` is ``edges`` or ``nodes``."""

    @abstractmethod
    def add_episodes(
        self,
        graph_id: str,
        texts: List[str],
        *,
        reference_time: Any = None,
        source_description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[str]:
        """Append runtime episodes (e.g. simulation activity) to the graph."""

    @abstractmethod
    def delete_graph(self, graph_id: str) -> None:
        """Remove every node/edge/episode belonging to ``graph_id``."""

    # -- Shared convenience helpers ------------------------------------------

    def get_all_nodes(self, graph_id: str) -> List[Dict[str, Any]]:
        """Enumerate nodes as plain dicts (uuid/name/labels/summary/attributes)."""

        data = self.get_graph_data(graph_id)
        return data.get("nodes", [])

    def get_all_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        """Enumerate edges as plain dicts (uuid/name/fact/source/target)."""

        data = self.get_graph_data(graph_id)
        return data.get("edges", [])

    def get_node_by_uuid(self, graph_id: str, node_uuid: str) -> Optional[Dict[str, Any]]:
        """Fetch one node by uuid, or ``None`` when absent."""

        for node in self.get_all_nodes(graph_id):
            if node.get("uuid") == node_uuid:
                return node
        return None
