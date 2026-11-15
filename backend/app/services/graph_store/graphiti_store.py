"""Graphiti-backed GraphStore implementation.

Graphiti (https://github.com/getzep/graphiti) is the open-source engine that
formerly powered MiroFish's Zep Cloud integration.  One Neo4j database hosts
every MiroFish graph; each graph is isolated by Graphiti's ``group_id``
namespace, which we alias as ``graph_id``.
"""

from __future__ import annotations

import asyncio
import hashlib
import threading
import time
import uuid as uuid_module
import warnings
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient

from ...config import Config
from ...utils.async_loop import run_async
from ...utils.logger import get_logger
from ...utils.ontology import (
    MAX_ONTOLOGY_TYPES,
    RESERVED_ONTOLOGY_ATTRIBUTE_NAMES,
    normalize_ontology_attributes,
)
from .base import (
    BatchCreatedCallback,
    GraphEdgeResult,
    GraphNodeResult,
    GraphStore,
    GraphStoreError,
    IngestionResult,
    ProgressCallback,
    SearchResult,
)
from .neo4j_client import get_driver, run_query

logger = get_logger("mirofish.graphiti_store")

# Concurrency for episode ingestion; Graphiti internally throttles LLM calls
# with SEMAPHORE_LIMIT, this bounds our concurrent add_episode coroutines.
INGEST_CONCURRENCY = 2
# 服务端临时故障（DeepSeek 502 等）需要足够长的退避才能熬过过载窗口
INGEST_CHUNK_RETRIES = 3
INGEST_RETRY_DELAYS = (5, 15, 45)
SEARCH_TIMEOUT_SECONDS = 60.0
EPISODE_TIMEOUT_SECONDS = 180.0


def _extract_first_json_object(text: str) -> str:
    """返回文本中首个完整 JSON 对象，解析失败时原样返回。"""

    import json as _json

    idx = text.find("{")
    if idx == -1:
        return text
    try:
        _obj, end = _json.JSONDecoder().raw_decode(text[idx:])
        return text[idx : idx + end]
    except ValueError:
        return text


class _JSONCleaningChatCompletions:
    """对 LLM 返回内容做截断清洗（如 DeepSeek 在 JSON 后附加的尾巴文本）。"""

    def __init__(self, inner):
        self._inner = inner

    async def create(self, **kwargs):
        response = await self._inner.create(**kwargs)
        try:
            choice = response.choices[0]
            content = choice.message.content or ""
            cleaned = _extract_first_json_object(content)
            if cleaned == content:
                return response
            new_message = choice.message.model_copy(update={"content": cleaned})
            new_choice = choice.model_copy(update={"message": new_message})
            return response.model_copy(update={"choices": [new_choice]})
        except Exception:  # noqa: BLE001 - 清洗失败不影响原始响应
            return response


class _JSONCleaningChat:
    def __init__(self, inner):
        self.completions = _JSONCleaningChatCompletions(inner.completions)


class _JSONCleaningAsyncOpenAIProxy:
    """只替换 chat.completions.create 的返回内容，其余委托原始 client。"""

    def __init__(self, inner):
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "chat", _JSONCleaningChat(inner.chat))

    def __getattr__(self, item):
        return getattr(object.__getattribute__(self, "_inner"), item)


class CompatOpenAIGenericClient(OpenAIGenericClient):
    """OpenAI 兼容端点的适配层，解决三类互操作问题：

    1. max_tokens 上限：部分端点（如 DeepSeek=8192）对输出上限有硬限制，
       配置 ``LLM_MAX_OUTPUT_TOKENS`` 后按上限钳制（缺省不钳制）。
    2. schema 镜像响应：部分端点会模仿 prompt 中 JSON Schema 的结构，
       把属性包在 ``properties`` 下或渲染成 {title,type,description,value}
       字段对象；graphiti 0.11.x 期望扁平属性，这里递归解包。
    3. JSON 尾巴文本：JSON 对象后附加额外文本会让 graphiti 的
       ``json.loads`` 报 Extra data，client 层先截取首个完整 JSON 对象。
    """

    def __init__(self, config=None, cache: bool = False, client: Any = None,
                 max_output_tokens_limit: Optional[int] = None):
        super().__init__(config=config, cache=cache, client=client)
        self.client = _JSONCleaningAsyncOpenAIProxy(self.client)
        self._max_output_tokens_limit = max_output_tokens_limit

    async def _generate_response(self, messages, response_model=None, max_tokens=4096,
                                 model_size=None) -> dict:
        clamped = max_tokens
        if self._max_output_tokens_limit:
            clamped = min(max_tokens or 4096, self._max_output_tokens_limit)
        result = await super()._generate_response(messages, response_model, clamped, model_size)
        return self._normalize_schema_mirroring(result)

    @staticmethod
    def _normalize_schema_mirroring(result: Any) -> Any:
        """递归解包 schema 镜像形态，非镜像响应原样返回。

        已知镜像形态（DeepSeek 等）：
        1. 顶层 ``properties`` 包装 → 展开到顶层
        2. 字段对象化 {title/type/description/anyOf/enum[, value]}：
           value 为原始值 → 取 value；value 缺失或为 null → 丢弃该键
           （graphiti 对缺失属性键有默认值回退）
        """

        schema_keys = {"type", "title", "description", "anyOf", "enum", "const"}
        drop = object()
        primitives = (str, int, float, bool)

        def unwrap(value: Any) -> Any:
            if isinstance(value, dict):
                keys = set(value.keys())
                if keys & schema_keys:
                    if "value" in value and isinstance(value["value"], primitives):
                        return value["value"]
                    return drop
                unwrapped = {k: unwrap(v) for k, v in value.items()}
                return {k: v for k, v in unwrapped.items() if v is not drop}
            if isinstance(value, list):
                return [unwrap(item) for item in value if unwrap(item) is not drop]
            return value

        if not isinstance(result, dict):
            return result

        merged = dict(result)
        if isinstance(merged.get("properties"), dict):
            inner = merged.pop("properties")
            for key, val in inner.items():
                merged.setdefault(key, val)

        unwrapped = {k: unwrap(v) for k, v in merged.items()}
        return {k: v for k, v in unwrapped.items() if v is not drop}


def _safe_attr_name(attr_name: str) -> str:
    """Convert reserved names into safe Pydantic attribute names."""

    if attr_name.lower() in RESERVED_ONTOLOGY_ATTRIBUTE_NAMES:
        return f"entity_{attr_name}"
    return attr_name


def build_entity_type_models(ontology: Dict[str, Any]) -> Dict[str, type]:
    """Build Graphiti custom entity types (Pydantic models) from an ontology dict.

    Mirrors the dynamic class construction the Zep integration used, but the
    resulting models subclass ``pydantic.BaseModel`` as Graphiti requires.
    """

    from pydantic import BaseModel, Field

    warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

    entity_types: Dict[str, type] = {}
    for entity_def in ontology.get("entity_types", [])[:MAX_ONTOLOGY_TYPES]:
        name = entity_def["name"]
        description = entity_def.get("description", f"A {name} entity.")

        attrs: Dict[str, Any] = {"__doc__": description}
        annotations: Dict[str, Any] = {}
        for normalized in normalize_ontology_attributes(entity_def.get("attributes", [])):
            attr_name = _safe_attr_name(normalized["name"])
            attrs[attr_name] = Field(description=normalized["description"], default=None)
            annotations[attr_name] = Optional[str]

        attrs["__annotations__"] = annotations
        entity_class = type(name, (BaseModel,), attrs)
        entity_class.__doc__ = description
        entity_types[name] = entity_class

    return entity_types


def build_edge_type_models(ontology: Dict[str, Any]) -> Dict[str, type]:
    """Build Graphiti custom edge types (Pydantic models) from an ontology dict."""

    from pydantic import BaseModel, Field

    edge_types: Dict[str, type] = {}
    for edge_def in ontology.get("edge_types", [])[:MAX_ONTOLOGY_TYPES]:
        name = edge_def["name"]
        description = edge_def.get("description", f"A {name} relationship.")

        attrs: Dict[str, Any] = {"__doc__": description}
        annotations: Dict[str, Any] = {}
        for normalized in normalize_ontology_attributes(edge_def.get("attributes", [])):
            attr_name = _safe_attr_name(normalized["name"])
            attrs[attr_name] = Field(description=normalized["description"], default=None)
            annotations[attr_name] = Optional[str]

        attrs["__annotations__"] = annotations
        class_name = "".join(word.capitalize() for word in name.split("_"))
        edge_class = type(class_name, (BaseModel,), attrs)
        edge_class.__doc__ = description
        edge_types[name] = edge_class

    return edge_types


class GraphitiStore(GraphStore):
    """Synchronous facade over graphiti-core executed on a shared loop."""

    def __init__(self):
        self._client_lock = threading.Lock()
        self._client: Any = None
        self._indices_ready = False
        # Ontology is set per graph right before ingestion; kept per graph id
        # so concurrent builds do not interfere.
        self._ontologies: Dict[str, Dict[str, Any]] = {}
        self._ontology_locks: Dict[str, threading.Lock] = {}

    # ------------------------------------------------------------------
    # Client construction
    # ------------------------------------------------------------------

    def _build_client(self) -> Any:
        """Construct one Graphiti client for the whole Neo4j database."""

        from graphiti_core import Graphiti
        from graphiti_core.cross_encoder.openai_reranker_client import (
            OpenAIRerankerClient,
        )
        from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
        from graphiti_core.llm_client.config import LLMConfig
        from openai import AsyncOpenAI

        llm_config = LLMConfig(
            api_key=Config.LLM_API_KEY or "",
            model=Config.LLM_MODEL_NAME,
            small_model=Config.LLM_MODEL_NAME,
            base_url=Config.LLM_BASE_URL,
        )
        llm_client = CompatOpenAIGenericClient(
            config=llm_config,
            max_output_tokens_limit=Config.LLM_MAX_OUTPUT_TOKENS,
        )

        embedder_config_kwargs: Dict[str, Any] = {
            "api_key": Config.EMBEDDING_API_KEY or "",
            "embedding_model": Config.EMBEDDING_MODEL_NAME,
            "base_url": Config.EMBEDDING_BASE_URL,
        }
        if Config.EMBEDDING_DIM:
            embedder_config_kwargs["embedding_dim"] = Config.EMBEDDING_DIM
        embedder = OpenAIEmbedder(config=OpenAIEmbedderConfig(**embedder_config_kwargs))

        return Graphiti(
            Config.NEO4J_URI,
            Config.NEO4J_USER,
            Config.NEO4J_PASSWORD,
            llm_client=llm_client,
            embedder=embedder,
            # Reuse the same OpenAI-compatible endpoint for reranking so no
            # extra service is required. (graphiti 0.11.x expects a raw
            # AsyncOpenAI client here.)
            cross_encoder=OpenAIRerankerClient(
                config=llm_config,
                client=AsyncOpenAI(
                    api_key=Config.LLM_API_KEY or "",
                    base_url=Config.LLM_BASE_URL,
                ),
            ),
        )

    def _get_client(self) -> Any:
        """Return the shared Graphiti client, building indices on first use."""

        if self._client is not None and self._indices_ready:
            return self._client

        with self._client_lock:
            if self._client is None:
                self._client = self._build_client()

            if not self._indices_ready:
                run_async(
                    self._client.build_indices_and_constraints(),
                    timeout=120.0,
                )
                self._indices_ready = True
                logger.info("Graphiti indices and constraints ensured")

            return self._client

    def _ontology_for(self, graph_id: str) -> Dict[str, Any]:
        with self._ontology_locks.get(graph_id, threading.Lock()):
            return self._ontologies.get(graph_id, {})

    # ------------------------------------------------------------------
    # Graph lifecycle
    # ------------------------------------------------------------------

    def create_graph(
        self,
        name: str,
        *,
        graph_id: Optional[str] = None,
        graph_id_callback=None,
    ) -> str:
        """Create a logical graph namespace.

        Neo4j needs no server-side object for an empty namespace, so this
        only mints the durable id (same ``mirofish_<hex16>`` shape as before)
        and lets the caller journal it before any mutation.
        """

        graph_id = graph_id or f"mirofish_{uuid_module.uuid4().hex[:16]}"
        if graph_id_callback:
            graph_id_callback(graph_id)
        return graph_id

    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]) -> None:
        """Attach the ontology used by subsequent ingestions of this graph."""

        with self._ontology_locks.setdefault(graph_id, threading.Lock()):
            self._ontologies[graph_id] = ontology or {}

    def delete_graph(self, graph_id: str) -> None:
        """Delete every node (and thereby edge/episode) in the namespace."""

        run_query(
            "MATCH (n {group_id: $gid}) DETACH DELETE n",
            {"gid": graph_id},
            operation_name=f"delete graph {graph_id}",
        )
        with self._ontology_locks.setdefault(graph_id, threading.Lock()):
            self._ontologies.pop(graph_id, None)

    def delete_graph_if_exists(self, graph_id: str) -> None:
        self.delete_graph(graph_id)

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def add_text_batches(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 350,
        progress_callback: Optional[ProgressCallback] = None,
        batch_created_callback: Optional[BatchCreatedCallback] = None,
    ) -> IngestionResult:
        """Ingest document chunks as Graphiti episodes and wait for completion.

        Graphiti processes each episode synchronously (LLM extraction runs
        inside ``add_episode``), so unlike the Zep Batch API there is no
        server-side queue to poll: completion is implied by return.
        """

        if not graph_id:
            raise ValueError("graph_id is required")
        if not chunks:
            raise ValueError("At least one text chunk is required")

        operation_id = hashlib.sha256(
            f"{graph_id}:{hashlib.sha256(chr(0).join(chunks).encode('utf-8')).hexdigest()}".encode(
                "utf-8"
            )
        ).hexdigest()
        if batch_created_callback:
            batch_created_callback(None, operation_id)
            batch_created_callback(f"graphiti-{graph_id}", operation_id)

        client = self._get_client()
        ontology = self._ontology_for(graph_id)
        entity_types = build_entity_type_models(ontology)
        # 注意：graphiti-core 0.11.x 的 add_episode 暂不支持自定义 edge_types
        # （受 camel-oasis 的 neo4j==5.23.0 钉版约束，只能使用 0.11.x）；
        # 边类型名仍保留在本体中供报告检索与前端展示使用。

        from graphiti_core.nodes import EpisodeType  # noqa: WPS433 - 版本适配

        total = len(chunks)
        results: List[Optional[str]] = [None] * total
        errors: List[str] = []

        async def _ingest() -> None:
            semaphore = asyncio.Semaphore(INGEST_CONCURRENCY)

            async def _one(index: int, chunk: str) -> None:
                async with semaphore:
                    last_error: Exception | None = None
                    for attempt in range(1, INGEST_CHUNK_RETRIES + 1):
                        try:
                            await client.add_episode(
                                name=f"MiroFish chunk {index}",
                                episode_body=chunk,
                                source=EpisodeType.text,
                                source_description="MiroFish source document chunk",
                                reference_time=datetime.now(timezone.utc),
                                group_id=graph_id,
                                entity_types=entity_types or None,
                            )
                            results[index] = f"episode-{index}"
                            return
                        except Exception as error:  # noqa: BLE001 - retried below
                            last_error = error
                            logger.warning(
                                "Episode %s/%s attempt %s failed: %s",
                                index + 1,
                                total,
                                attempt,
                                error,
                            )
                            await asyncio.sleep(
                                INGEST_RETRY_DELAYS[min(attempt - 1, len(INGEST_RETRY_DELAYS) - 1)]
                            )
                    errors.append(f"chunk {index}: {last_error}")

            tasks = [_one(i, chunk) for i, chunk in enumerate(chunks)]
            done = 0

            # Report progress as individual episodes complete.
            for coro in asyncio.as_completed(tasks):
                await coro
                done += 1
                if progress_callback:
                    progress_callback(
                        f"ingested {done}/{total} chunks",
                        done / total,
                    )

        run_async(_ingest(), timeout=max(600.0, total * 30.0))

        if errors:
            raise GraphStoreError(
                f"{len(errors)}/{total} chunks failed ingestion; first error: {errors[0]}"
            )

        return IngestionResult(
            episode_uuids=[r for r in results if r],
            item_count=total,
            operation_id=operation_id,
        )

    def add_episodes(
        self,
        graph_id: str,
        texts: List[str],
        *,
        reference_time=None,
        source_description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        progress_callback=None,
    ) -> List[str]:
        """Append runtime episodes (e.g. simulation activity) to the graph."""

        if not texts:
            return []

        client = self._get_client()
        when = reference_time or datetime.now(timezone.utc)
        if isinstance(when, str):
            try:
                when = datetime.fromisoformat(when.replace("Z", "+00:00"))
            except ValueError:
                when = datetime.now(timezone.utc)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)

        from graphiti_core.nodes import EpisodeType  # noqa: WPS433 - 版本适配

        suffix = hashlib.sha256(
            f"{graph_id}:{''.join(texts)}".encode("utf-8")
        ).hexdigest()[:12]
        episode_uuids: List[str] = []

        for index, text in enumerate(texts):
            run_async(
                client.add_episode(
                    name=f"MiroFish activity {suffix}-{index}",
                    episode_body=text,
                    source=EpisodeType.text,
                    source_description=source_description or "MiroFish simulation activity",
                    reference_time=when,
                    group_id=graph_id,
                ),
                timeout=EPISODE_TIMEOUT_SECONDS,
            )
            episode_uuids.append(f"{suffix}-{index}")
            if progress_callback:
                progress_callback(index + 1, len(texts))

        return episode_uuids

    # ------------------------------------------------------------------
    # Enumeration
    # ------------------------------------------------------------------

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        """Enumerate nodes/edges of one graph via direct Neo4j queries."""

        node_rows = run_query(
            "MATCH (n:Entity {group_id: $gid}) "
            "RETURN n.uuid AS uuid, n.name AS name, labels(n) AS labels, "
            "n.summary AS summary, n.attributes AS attributes, "
            "toString(n.created_at) AS created_at "
            "ORDER BY n.created_at",
            {"gid": graph_id},
            operation_name=f"fetch nodes {graph_id}",
        )

        edge_rows = run_query(
            "MATCH (a:Entity {group_id: $gid})-[r:RELATES_TO {group_id: $gid}]->"
            "(b:Entity {group_id: $gid}) "
            "RETURN r.uuid AS uuid, r.name AS name, "
            "coalesce(r.fact_text, r.fact, '') AS fact, "
            "a.uuid AS source_node_uuid, b.uuid AS target_node_uuid, "
            "r.attributes AS attributes, toString(r.created_at) AS created_at, "
            "toString(r.valid_at) AS valid_at, toString(r.invalid_at) AS invalid_at, "
            "toString(r.expired_at) AS expired_at, "
            "coalesce(r.episodes, []) AS episodes "
            "ORDER BY r.created_at",
            {"gid": graph_id},
            operation_name=f"fetch edges {graph_id}",
        )

        nodes: List[Dict[str, Any]] = []
        for row in node_rows:
            labels = [label for label in (row.get("labels") or []) if label != "Entity"]
            created_at = row.get("created_at")
            if created_at and created_at.startswith("None"):
                created_at = None
            nodes.append(
                {
                    "uuid": row.get("uuid") or "",
                    "name": row.get("name") or "",
                    "labels": labels or ["Entity"],
                    "summary": row.get("summary") or "",
                    "attributes": row.get("attributes") or {},
                    "created_at": created_at,
                }
            )

        edges: List[Dict[str, Any]] = []
        for row in edge_rows:
            attributes = row.get("attributes") or {}
            if isinstance(attributes, str):
                # Older graphiti versions serialize attributes as JSON strings.
                import json as _json

                try:
                    attributes = _json.loads(attributes)
                except (ValueError, TypeError):
                    attributes = {"value": attributes}
            episodes = row.get("episodes") or []
            if isinstance(episodes, str):
                episodes = [episodes]
            edges.append(
                {
                    "uuid": row.get("uuid") or "",
                    "name": row.get("name") or "",
                    "fact": row.get("fact") or "",
                    "fact_type": row.get("name") or "",
                    "source_node_uuid": row.get("source_node_uuid") or "",
                    "target_node_uuid": row.get("target_node_uuid") or "",
                    "attributes": attributes,
                    "created_at": row.get("created_at"),
                    "valid_at": row.get("valid_at"),
                    "invalid_at": row.get("invalid_at"),
                    "expired_at": row.get("expired_at"),
                    "episodes": episodes,
                }
            )

        return {
            "graph_id": graph_id,
            "nodes": nodes,
            "edges": edges,
            "node_count": len(nodes),
            "edge_count": len(edges),
        }

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        graph_id: str,
        query: str,
        limit: int = 10,
        scope: str = "edges",
    ) -> SearchResult:
        """Hybrid semantic search scoped to one graph namespace."""

        normalized_query = (query or "").strip()
        if not normalized_query:
            return SearchResult()
        normalized_query = normalized_query[:400]
        limit = max(1, min(int(limit), 50))

        result = SearchResult()
        if scope in ("edges", "both"):
            result.edges = self._search_edges(graph_id, normalized_query, limit)
        if scope in ("nodes", "both"):
            result.nodes = self._search_nodes(graph_id, normalized_query, limit)
        return result

    def _search_edges(
        self, graph_id: str, query: str, limit: int
    ) -> List[GraphEdgeResult]:
        """Edge search via Graphiti's hybrid fact search."""

        client = self._get_client()
        try:
            edges = run_async(
                client.search(query, group_ids=[graph_id], num_results=limit),
                timeout=SEARCH_TIMEOUT_SECONDS,
            )
        except Exception as error:  # noqa: BLE001
            logger.warning(
                "Graphiti edge search failed for %s (%s); falling back to fulltext",
                graph_id,
                error,
            )
            return self._fallback_edge_search(graph_id, query, limit)

        results: List[GraphEdgeResult] = []
        for edge in edges or []:
            results.append(
                GraphEdgeResult(
                    uuid=getattr(edge, "uuid", "") or "",
                    name=getattr(edge, "name", "") or "",
                    fact=getattr(edge, "fact", "") or getattr(edge, "fact_text", "") or "",
                    source_node_uuid=getattr(edge, "source_node_uuid", "") or "",
                    target_node_uuid=getattr(edge, "target_node_uuid", "") or "",
                    created_at=_to_iso(getattr(edge, "created_at", None)),
                    valid_at=_to_iso(getattr(edge, "valid_at", None)),
                    invalid_at=_to_iso(getattr(edge, "invalid_at", None)),
                    expired_at=_to_iso(getattr(edge, "expired_at", None)),
                    attributes=getattr(edge, "attributes", {}) or {},
                )
            )
        return results

    def _search_nodes(
        self, graph_id: str, query: str, limit: int
    ) -> List[GraphNodeResult]:
        """Node search via embedding cosine similarity with fulltext fallback."""

        embedding = self._embed_query(query)
        if embedding:
            try:
                # graphiti 0.11.x 将向量存为节点属性（无向量索引），采用其
                # 内部相同的余弦相似度查询方式。
                rows = run_query(
                    "MATCH (n:Entity {group_id: $gid}) "
                    "WHERE n.name_embedding IS NOT NULL "
                    "WITH n, vector.similarity.cosine(n.name_embedding, $embedding) AS score "
                    "RETURN n.uuid AS uuid, n.name AS name, labels(n) AS labels, "
                    "n.summary AS summary, n.attributes AS attributes, "
                    "toString(n.created_at) AS created_at, score "
                    "ORDER BY score DESC LIMIT $limit",
                    {"gid": graph_id, "limit": limit, "embedding": embedding},
                    operation_name=f"embedding node search {graph_id}",
                )
                return [self._node_from_row(row) for row in rows]
            except Exception as error:  # noqa: BLE001
                logger.warning(
                    "Embedding node search failed for %s (%s); trying fulltext",
                    graph_id,
                    error,
                )

        try:
            rows = run_query(
                "CALL db.index.fulltext.queryNodes('node_name_and_summary', $query) "
                "YIELD node, score "
                "WHERE node.group_id = $gid "
                "RETURN node.uuid AS uuid, node.name AS name, labels(node) AS labels, "
                "node.summary AS summary, node.attributes AS attributes, "
                "toString(node.created_at) AS created_at, score "
                "ORDER BY score DESC LIMIT $limit",
                {"gid": graph_id, "query": query, "limit": limit},
                operation_name=f"fulltext node search {graph_id}",
            )
            return [self._node_from_row(row) for row in rows]
        except Exception as error:  # noqa: BLE001
            logger.warning(
                "Fulltext node search failed for %s (%s); falling back to scan",
                graph_id,
                error,
            )

        # Last resort: in-memory substring ranking over an enumerated graph.
        lowered = query.lower()
        nodes = self.get_graph_data(graph_id).get("nodes", [])
        scored = [
            (node, _substring_score(lowered, node))
            for node in nodes
        ]
        scored = [(n, s) for n, s in scored if s > 0]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return [
            GraphNodeResult(
                uuid=n["uuid"],
                name=n.get("name", ""),
                labels=n.get("labels", []),
                summary=n.get("summary", ""),
                attributes=n.get("attributes", {}),
            )
            for n, _ in scored[:limit]
        ]

    def _fallback_edge_search(
        self, graph_id: str, query: str, limit: int
    ) -> List[GraphEdgeResult]:
        """Fulltext-based edge search when the Graphiti pipeline is unavailable."""

        try:
            rows = run_query(
                "CALL db.index.fulltext.queryRelationships('edge_name_and_fact', $query) "
                "YIELD edge, score "
                "WHERE edge.group_id = $gid "
                "RETURN edge.uuid AS uuid, edge.name AS name, "
                "coalesce(edge.fact_text, edge.fact, '') AS fact, "
                "edge.source_node_uuid AS source_node_uuid, "
                "edge.target_node_uuid AS target_node_uuid, score "
                "ORDER BY score DESC LIMIT $limit",
                {"gid": graph_id, "query": query, "limit": limit},
                operation_name=f"fulltext edge search {graph_id}",
            )
            return [
                GraphEdgeResult(
                    uuid=row.get("uuid") or "",
                    name=row.get("name") or "",
                    fact=row.get("fact") or "",
                    source_node_uuid=row.get("source_node_uuid") or "",
                    target_node_uuid=row.get("target_node_uuid") or "",
                )
                for row in rows
            ]
        except Exception as error:  # noqa: BLE001
            logger.warning("Fulltext edge search failed for %s: %s", graph_id, error)
            return []

    def _embed_query(self, query: str) -> Optional[List[float]]:
        """Compute a query embedding, or ``None`` when the endpoint fails."""

        client = self._get_client()
        try:
            embedder = getattr(client, "embedder", None)
            if embedder is None:
                return None
            return run_async(embedder.create(input_data=[query]), timeout=30.0)
        except Exception as error:  # noqa: BLE001
            logger.warning("Query embedding failed: %s", error)
            return None

    @staticmethod
    def _node_from_row(row: Dict[str, Any]) -> GraphNodeResult:
        labels = [label for label in (row.get("labels") or []) if label != "Entity"]
        return GraphNodeResult(
            uuid=row.get("uuid") or "",
            name=row.get("name") or "",
            labels=labels or ["Entity"],
            summary=row.get("summary") or "",
            attributes=row.get("attributes") or {},
            created_at=row.get("created_at"),
        )


def _to_iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _substring_score(query: str, node: Dict[str, Any]) -> int:
    name = (node.get("name") or "").lower()
    summary = (node.get("summary") or "").lower()
    score = 0
    for token in query.split():
        if token and token in name:
            score += 2
        if token and token in summary:
            score += 1
    return score
