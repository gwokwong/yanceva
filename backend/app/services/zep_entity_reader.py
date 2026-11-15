"""
实体读取与过滤服务
从 Graphiti/Neo4j 图谱中读取节点，筛选出符合预定义实体类型的节点

（原实现基于 Zep Cloud；迁移后通过 GraphStore 直接查询 Neo4j，
对上层保持相同的数据结构与调用方式。）
"""

from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field

from ..utils.logger import get_logger
from .graph_store import get_graph_store
from .graph_store.neo4j_client import run_query

logger = get_logger('mirofish.entity_reader')


@dataclass
class EntityNode:
    """实体节点数据结构"""
    uuid: str
    name: str
    labels: List[str]
    summary: str
    attributes: Dict[str, Any]
    # 相关的边信息
    related_edges: List[Dict[str, Any]] = field(default_factory=list)
    # 相关的其他节点信息
    related_nodes: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes,
            "related_edges": self.related_edges,
            "related_nodes": self.related_nodes,
        }

    def get_entity_type(self) -> Optional[str]:
        """获取实体类型（排除默认的Entity标签）"""
        for label in self.labels:
            if label not in ["Entity", "Node"]:
                return label
        return None


@dataclass
class FilteredEntities:
    """过滤后的实体集合"""
    entities: List[EntityNode]
    entity_types: Set[str]
    total_count: int
    filtered_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entities": [e.to_dict() for e in self.entities],
            "entity_types": list(self.entity_types),
            "total_count": self.total_count,
            "filtered_count": self.filtered_count,
        }


class ZepEntityReader:
    """
    实体读取与过滤服务（Graphiti/Neo4j 后端）

    主要功能：
    1. 从图谱读取所有节点
    2. 筛选出符合预定义实体类型的节点（Labels不只是Entity的节点）
    3. 获取每个实体的相关边和关联节点信息
    """

    def __init__(self, api_key: Optional[str] = None):
        # api_key 仅为向后兼容保留；Neo4j 配置来自环境变量。
        self.store = get_graph_store()

    def _node_query(self, graph_id: str, node_uuid: Optional[str] = None) -> List[Dict[str, Any]]:
        """Query entity nodes (optionally one) of a graph from Neo4j."""

        params: Dict[str, Any] = {"gid": graph_id}
        if node_uuid:
            rows = run_query(
                "MATCH (n:Entity {group_id: $gid, uuid: $uuid}) "
                "RETURN n.uuid AS uuid, n.name AS name, labels(n) AS labels, "
                "n.summary AS summary, n.attributes AS attributes",
                {**params, "uuid": node_uuid},
                operation_name=f"fetch node {node_uuid}",
            )
        else:
            rows = run_query(
                "MATCH (n:Entity {group_id: $gid}) "
                "RETURN n.uuid AS uuid, n.name AS name, labels(n) AS labels, "
                "n.summary AS summary, n.attributes AS attributes "
                "ORDER BY n.name",
                params,
                operation_name=f"fetch nodes {graph_id}",
            )

        nodes_data = []
        for row in rows:
            attributes = row.get("attributes") or {}
            if isinstance(attributes, str):
                import json as _json

                try:
                    attributes = _json.loads(attributes)
                except (ValueError, TypeError):
                    attributes = {"value": attributes}
            labels = row.get("labels") or ["Entity"]
            nodes_data.append({
                "uuid": row.get("uuid") or "",
                "name": row.get("name") or "",
                "labels": labels,
                "summary": row.get("summary") or "",
                "attributes": attributes,
            })
        return nodes_data

    def _edge_query(self, graph_id: str) -> List[Dict[str, Any]]:
        """Query every RELATES_TO edge of a graph from Neo4j."""

        rows = run_query(
            "MATCH (a:Entity {group_id: $gid})-[r:RELATES_TO {group_id: $gid}]->"
            "(b:Entity {group_id: $gid}) "
            "RETURN r.uuid AS uuid, r.name AS name, "
            "coalesce(r.fact_text, r.fact, '') AS fact, "
            "a.uuid AS source_node_uuid, b.uuid AS target_node_uuid, "
            "r.attributes AS attributes",
            {"gid": graph_id},
            operation_name=f"fetch edges {graph_id}",
        )

        edges_data = []
        for row in rows:
            attributes = row.get("attributes") or {}
            if isinstance(attributes, str):
                import json as _json

                try:
                    attributes = _json.loads(attributes)
                except (ValueError, TypeError):
                    attributes = {"value": attributes}
            edges_data.append({
                "uuid": row.get("uuid") or "",
                "name": row.get("name") or "",
                "fact": row.get("fact") or "",
                "source_node_uuid": row.get("source_node_uuid") or "",
                "target_node_uuid": row.get("target_node_uuid") or "",
                "attributes": attributes,
            })
        return edges_data

    def get_all_nodes(self, graph_id: str) -> List[Dict[str, Any]]:
        """
        获取图谱的所有节点

        Args:
            graph_id: 图谱ID

        Returns:
            节点列表
        """
        logger.info(f"获取图谱 {graph_id} 的所有节点...")
        nodes_data = self._node_query(graph_id)
        logger.info(f"共获取 {len(nodes_data)} 个节点")
        return nodes_data

    def get_all_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        """
        获取图谱的所有边

        Args:
            graph_id: 图谱ID

        Returns:
            边列表
        """
        logger.info(f"获取图谱 {graph_id} 的所有边...")
        edges_data = self._edge_query(graph_id)
        logger.info(f"共获取 {len(edges_data)} 条边")
        return edges_data

    def get_node_edges(
        self,
        node_uuid: str,
        *,
        graph_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        获取指定节点的相关边（双向完整关系）。

        Args:
            node_uuid: 节点UUID
            graph_id: 图谱ID；提供时保证返回双向完整关系

        Returns:
            边列表
        """
        if not graph_id:
            raise ValueError("graph_id is required for bidirectional edge lookup")

        try:
            return [
                edge
                for edge in self._edge_query(graph_id)
                if edge["source_node_uuid"] == node_uuid
                or edge["target_node_uuid"] == node_uuid
            ]
        except Exception as e:
            # An empty edge list is valid data. Authentication, permission and
            # transport failures must not be made indistinguishable from it.
            logger.error(f"获取节点 {node_uuid} 的边失败: {str(e)}")
            raise

    def filter_defined_entities(
        self,
        graph_id: str,
        defined_entity_types: Optional[List[str]] = None,
        enrich_with_edges: bool = True
    ) -> FilteredEntities:
        """
        筛选出符合预定义实体类型的节点

        筛选逻辑：
        - 如果节点的Labels只有一个"Entity"，说明这个实体不符合我们预定义的类型，跳过
        - 如果节点的Labels包含除"Entity"和"Node"之外的标签，说明符合预定义类型，保留

        Args:
            graph_id: 图谱ID
            defined_entity_types: 预定义的实体类型列表（可选，如果提供则只保留这些类型）
            enrich_with_edges: 是否获取每个实体的相关边信息

        Returns:
            FilteredEntities: 过滤后的实体集合
        """
        logger.info(f"开始筛选图谱 {graph_id} 的实体...")

        # 获取所有节点
        all_nodes = self.get_all_nodes(graph_id)
        total_count = len(all_nodes)

        # 获取所有边（用于后续关联查找）
        all_edges = self.get_all_edges(graph_id) if enrich_with_edges else []

        # 构建节点UUID到节点数据的映射
        node_map = {n["uuid"]: n for n in all_nodes}

        # 筛选符合条件的实体
        filtered_entities = []
        entity_types_found = set()

        for node in all_nodes:
            labels = node.get("labels", [])

            # 筛选逻辑：Labels必须包含除"Entity"和"Node"之外的标签
            custom_labels = [l for l in labels if l not in ["Entity", "Node"]]

            if not custom_labels:
                # 只有默认标签，跳过
                continue

            # 如果指定了预定义类型，检查是否匹配
            if defined_entity_types:
                matching_labels = [l for l in custom_labels if l in defined_entity_types]
                if not matching_labels:
                    continue
                entity_type = matching_labels[0]
            else:
                entity_type = custom_labels[0]

            entity_types_found.add(entity_type)

            # 创建实体节点对象
            entity = EntityNode(
                uuid=node["uuid"],
                name=node["name"],
                labels=labels,
                summary=node["summary"],
                attributes=node["attributes"],
            )

            # 获取相关边和节点
            if enrich_with_edges:
                related_edges = []
                related_node_uuids = set()

                for edge in all_edges:
                    if edge["source_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "outgoing",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "target_node_uuid": edge["target_node_uuid"],
                        })
                        related_node_uuids.add(edge["target_node_uuid"])
                    elif edge["target_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "incoming",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "source_node_uuid": edge["source_node_uuid"],
                        })
                        related_node_uuids.add(edge["source_node_uuid"])

                entity.related_edges = related_edges

                # 获取关联节点的基本信息
                related_nodes = []
                for related_uuid in related_node_uuids:
                    if related_uuid in node_map:
                        related_node = node_map[related_uuid]
                        related_nodes.append({
                            "uuid": related_node["uuid"],
                            "name": related_node["name"],
                            "labels": related_node["labels"],
                            "summary": related_node.get("summary", ""),
                        })

                entity.related_nodes = related_nodes

            filtered_entities.append(entity)

        logger.info(f"筛选完成: 总节点 {total_count}, 符合条件 {len(filtered_entities)}, "
                   f"实体类型: {entity_types_found}")

        return FilteredEntities(
            entities=filtered_entities,
            entity_types=entity_types_found,
            total_count=total_count,
            filtered_count=len(filtered_entities),
        )

    def get_entity_with_context(
        self,
        graph_id: str,
        entity_uuid: str
    ) -> Optional[EntityNode]:
        """
        获取单个实体及其完整上下文（边和关联节点）

        Args:
            graph_id: 图谱ID
            entity_uuid: 实体UUID

        Returns:
            EntityNode或None
        """
        try:
            nodes = self._node_query(graph_id, node_uuid=entity_uuid)
            if not nodes:
                return None
            node = nodes[0]

            # 获取节点的边
            edges = self.get_node_edges(entity_uuid, graph_id=graph_id)

            # 获取所有节点用于关联查找
            all_nodes = self.get_all_nodes(graph_id)
            node_map = {n["uuid"]: n for n in all_nodes}

            # 处理相关边和节点
            related_edges = []
            related_node_uuids = set()

            for edge in edges:
                if edge["source_node_uuid"] == entity_uuid:
                    related_edges.append({
                        "direction": "outgoing",
                        "edge_name": edge["name"],
                        "fact": edge["fact"],
                        "target_node_uuid": edge["target_node_uuid"],
                    })
                    related_node_uuids.add(edge["target_node_uuid"])
                else:
                    related_edges.append({
                        "direction": "incoming",
                        "edge_name": edge["name"],
                        "fact": edge["fact"],
                        "source_node_uuid": edge["source_node_uuid"],
                    })
                    related_node_uuids.add(edge["source_node_uuid"])

            # 获取关联节点信息
            related_nodes = []
            for related_uuid in related_node_uuids:
                if related_uuid in node_map:
                    related_node = node_map[related_uuid]
                    related_nodes.append({
                        "uuid": related_node["uuid"],
                        "name": related_node["name"],
                        "labels": related_node["labels"],
                        "summary": related_node.get("summary", ""),
                    })

            return EntityNode(
                uuid=node["uuid"],
                name=node["name"],
                labels=node["labels"],
                summary=node["summary"],
                attributes=node["attributes"],
                related_edges=related_edges,
                related_nodes=related_nodes,
            )

        except Exception as e:
            # Missing nodes return ``None``; transport/config failures propagate
            # so callers cannot prepare a simulation with silently incomplete
            # graph context.
            logger.error(f"获取实体 {entity_uuid} 失败: {str(e)}")
            raise

    def get_entities_by_type(
        self,
        graph_id: str,
        entity_type: str,
        enrich_with_edges: bool = True
    ) -> List[EntityNode]:
        """
        获取指定类型的所有实体

        Args:
            graph_id: 图谱ID
            entity_type: 实体类型（如 "Student", "Consumer" 等）
            enrich_with_edges: 是否获取相关边信息

        Returns:
            实体列表
        """
        result = self.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=[entity_type],
            enrich_with_edges=enrich_with_edges
        )
        return result.entities
