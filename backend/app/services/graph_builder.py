"""
图谱构建服务
基于 Graphiti + Neo4j 构建知识图谱（取代原 Zep Cloud 集成）

对上层 API 保持与原 Zep 版本相同的方法签名；批量协调（Batch API 轮询/
幂等对账）不再需要——Graphiti 的 add_episode 在返回时即完成 LLM 抽取，
因此 ``_wait_for_batch`` 退化为进度透传。
"""

import hashlib
import uuid
import threading
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass

from ..models.task import TaskManager, TaskStatus
from ..utils.locale import t, get_locale, set_locale
from ..utils.logger import get_logger
from .graph_store import get_graph_store
from .text_processor import TextProcessor

logger = get_logger("mirofish.graph_builder")

# 与原 Zep Batch API 对齐的单块大小上限（字符数）
MAX_CHUNK_CHARS = 10_000
MAX_CHUNK_COUNT = 50_000


@dataclass
class GraphInfo:
    """图谱信息"""
    graph_id: str
    node_count: int
    edge_count: int
    entity_types: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "entity_types": self.entity_types,
        }


@dataclass(frozen=True)
class BatchSubmission:
    """Ingestion identity kept for API compatibility and build journaling."""

    batch_id: str
    operation_id: str
    episode_uuids: List[str]
    item_count: int


class GraphBuilderService:
    """
    图谱构建服务
    负责通过 Graphiti + Neo4j 构建知识图谱
    """

    def __init__(self, api_key: Optional[str] = None):
        # api_key 参数仅为向后兼容保留；图谱后端配置来自 NEO4J_*/EMBEDDING_*。
        self.store = get_graph_store()
        self.task_manager = TaskManager()

    def build_graph_async(
        self,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str = "MiroFish Graph",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        batch_size: int = 350
    ) -> str:
        """
        异步构建图谱（保留旧入口；主流程走 graph.py 的任务包装）

        Returns:
            任务ID
        """
        task_id = self.task_manager.create_task(
            task_type="graph_build",
            metadata={
                "graph_name": graph_name,
                "chunk_size": chunk_size,
                "text_length": len(text),
            }
        )

        current_locale = get_locale()

        thread = threading.Thread(
            target=self._build_graph_worker,
            args=(task_id, text, ontology, graph_name, chunk_size, chunk_overlap, batch_size, current_locale)
        )
        thread.daemon = True
        thread.start()

        return task_id

    def _build_graph_worker(
        self,
        task_id: str,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str,
        chunk_size: int,
        chunk_overlap: int,
        batch_size: int,
        locale: str = 'zh'
    ):
        """图谱构建工作线程"""
        set_locale(locale)
        try:
            self.task_manager.update_task(
                task_id,
                status=TaskStatus.PROCESSING,
                progress=5,
                message=t('progress.startBuildingGraph')
            )

            chunks = TextProcessor.split_text(text, chunk_size, chunk_overlap)
            self.validate_batch_chunks(chunks, batch_size=batch_size)
            total_chunks = len(chunks)

            graph_id = self.create_graph(graph_name)
            self.task_manager.update_task(
                task_id,
                progress=10,
                message=t('progress.graphCreated', graphId=graph_id)
            )

            self.set_ontology(graph_id, ontology)
            self.task_manager.update_task(
                task_id,
                progress=15,
                message=t('progress.ontologySet')
            )

            self.task_manager.update_task(
                task_id,
                progress=20,
                message=t('progress.textSplit', count=total_chunks)
            )

            submission = self.add_text_batches(
                graph_id, chunks, batch_size,
                lambda msg, prog: self.task_manager.update_task(
                    task_id,
                    progress=20 + int(prog * 0.4),
                    message=msg
                )
            )

            self.task_manager.update_task(
                task_id,
                progress=60,
                message=t('progress.waitingZepProcess')
            )

            self._wait_for_batch(
                submission,
                lambda msg, prog: self.task_manager.update_task(
                    task_id,
                    progress=60 + int(prog * 0.3),
                    message=msg
                )
            )

            self.task_manager.update_task(
                task_id,
                progress=90,
                message=t('progress.fetchingGraphInfo')
            )

            graph_info = self._get_graph_info(graph_id)

            self.task_manager.complete_task(task_id, {
                "graph_id": graph_id,
                "graph_info": graph_info.to_dict(),
                "chunks_processed": total_chunks,
            })

        except Exception as e:
            import traceback
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            self.task_manager.fail_task(task_id, error_msg)

    def create_graph(
        self,
        name: str,
        *,
        graph_id: str | None = None,
        graph_id_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Create a graph with a caller-durable ID (namespace in Neo4j)."""

        return self.store.create_graph(
            name,
            graph_id=graph_id,
            graph_id_callback=graph_id_callback,
        )

    @staticmethod
    def build_operation_id(graph_id: str, chunks: List[str]) -> str:
        payload_hash = hashlib.sha256("\0".join(chunks).encode("utf-8")).hexdigest()
        return hashlib.sha256(
            f"{graph_id}:{payload_hash}".encode("utf-8")
        ).hexdigest()

    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]):
        """设置图谱本体（公开方法；本体在摄取时转换为 Graphiti 自定义类型）"""
        self.store.set_ontology(graph_id, ontology)

    def add_text_batches(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 350,
        progress_callback: Optional[Callable] = None,
        batch_created_callback: Optional[Callable[[str | None, str], None]] = None,
    ) -> BatchSubmission:
        """Ingest document chunks into the graph and wait until processed."""

        result = self.store.add_text_batches(
            graph_id,
            chunks,
            batch_size=batch_size,
            progress_callback=progress_callback,
            batch_created_callback=batch_created_callback,
        )
        return BatchSubmission(
            batch_id=f"graphiti-{graph_id}",
            operation_id=result.operation_id,
            episode_uuids=result.episode_uuids,
            item_count=result.item_count,
        )

    @staticmethod
    def validate_batch_chunks(chunks: List[str], *, batch_size: int = 350) -> None:
        """Validate ingestion limits before the first mutation."""

        if not chunks:
            raise ValueError("At least one text chunk is required")
        if len(chunks) > MAX_CHUNK_COUNT:
            raise ValueError(f"Ingestion cannot contain more than {MAX_CHUNK_COUNT} chunks")
        oversized = [
            index for index, chunk in enumerate(chunks) if len(chunk) > MAX_CHUNK_CHARS
        ]
        if oversized:
            raise ValueError(
                f"Chunk exceeds {MAX_CHUNK_CHARS} characters at chunk {oversized[0]}"
            )

    def get_batch_summary(self, batch_id: str) -> Any:
        """Read a persisted batch identity for restart reconciliation.

        Graphiti ingestion is synchronous inside ``add_text_batches``; there
        is no server-side batch to resume, so callers treat a persisted batch
        as always-terminal.
        """

        return None

    def _wait_for_batch(
        self,
        submission: BatchSubmission,
        progress_callback: Optional[Callable] = None,
        timeout: int | None = None,
    ) -> List[str]:
        """No-op wait: Graphiti episodes are processed before this returns."""

        if progress_callback:
            progress_callback(
                t(
                    'progress.processingComplete',
                    completed=submission.item_count,
                    total=submission.item_count,
                ),
                1.0,
            )
        return list(submission.episode_uuids)

    def _get_graph_info(self, graph_id: str) -> GraphInfo:
        """获取图谱信息"""
        data = self.store.get_graph_data(graph_id)

        entity_types = set()
        for node in data.get("nodes", []):
            for label in node.get("labels", []) or []:
                if label not in ["Entity", "Node"]:
                    entity_types.add(label)

        return GraphInfo(
            graph_id=graph_id,
            node_count=data.get("node_count", 0),
            edge_count=data.get("edge_count", 0),
            entity_types=list(entity_types)
        )

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        """
        获取完整图谱数据（包含详细信息）
        """
        return self.store.get_graph_data(graph_id)

    def delete_graph(self, graph_id: str):
        """删除图谱（幂等：命名空间本就不存在时同样成功）"""
        self.store.delete_graph(graph_id)
