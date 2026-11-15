"""Graphiti 全闭环冒烟脚本（无需 LLM API key）。

用确定性的假 LLM / Embedding / Reranker 注入 Graphiti，对**真实 Neo4j**
跑通 MiroFish 的完整图谱链路：

    建索引 → 设本体 → 摄取文档块（实体/边抽取）→ 落库枚举 →
    语义检索（边+节点）→ 模拟活动回写 → 清理删除

这验证了 graphiti_store 的全部代码路径（本体转换、episode 摄取、
Neo4j 枚举查询、余弦/全文检索、命名空间删除），把"LLM 抽取质量"从
链路验证中隔离出来——后者需要真实 API key，用
``validate_graphiti_integration.py`` 验证。

用法：cd backend && NEO4J_PASSWORD=xxx uv run python scripts/validate_graphiti_full_loop.py
"""

import asyncio
import hashlib
import sys
from pathlib import Path
from typing import Any, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.llm_client.client import LLMClient
from graphiti_core.llm_client.config import LLMConfig

from app.config import Config  # noqa: E402
from app.services.graph_store.neo4j_client import (  # noqa: E402
    get_driver,
    run_query,
    validate_neo4j_config,
)

GRAPH_ID = "mirofish_smoke_selfcheck"

# ── 假 LLM：按响应模型派发，覆盖 add_episode 的全部 LLM 调用点 ──

NODE_A = "冒烟消费者张三"
NODE_B = "冒烟降噪耳机X"


class SmokeLLMClient(LLMClient):
    """确定性假 LLM：实现抽象方法 ``_generate_response``，返回纯 dict
    （与 0.11.6 内置客户端一致），覆盖 add_episode 全部 LLM 调用点。"""

    def __init__(self):
        super().__init__(LLMConfig(api_key="smoke", model="smoke"))
        self.calls: List[str] = []
        # 记录最近一次抽取的实体（resolve_extracted_nodes 需要为
        # 每个抽取节点返回一条消解记录，否则 0.11.x 会丢弃全部实体；
        # 且消解记录的 name 会覆盖抽取名，需回填真实实体名）
        self._last_extracted_count = 0
        self._last_extracted_names: List[str] = []

    async def _generate_response(self, messages, response_model=None, max_tokens=4096,
                                 model_size=None) -> dict:
        self.calls.append(response_model.__name__ if response_model else "dict")

        if response_model is None:
            # extract_nodes reflexion / dedupe_nodes / dedupe_edges 等裸 dict 调用点
            return {"missed_entities": [], "duplicates": []}

        name = response_model.__name__

        if name == "ExtractedEntities":
            # graphiti 0.11.x 的类型表 id 0 是内置 'Entity' 兜底，自定义类型
            # 从 1 开始。类型表随 prompt 注入（repr 形式），解析可用上限以
            # 同时适配「带本体的图谱摄取」与「无本体的模拟活动回写」两条路径。
            import re as _re

            prompt_text = messages[-1].content if messages else ""
            available_ids = [
                int(m) for m in _re.findall(r"'entity_type_id':\s*(\d+)", prompt_text)
            ]
            max_id = max(available_ids) if available_ids else 0
            if max_id >= 2:
                first_id, second_id = 1, 2
            else:
                first_id = second_id = 0  # 只剩内置 Entity 类型可用
            self._last_extracted_count = 2
            self._last_extracted_names = [NODE_A, NODE_B]
            return {"extracted_entities": [
                {"name": NODE_A, "entity_type_id": first_id},
                {"name": NODE_B, "entity_type_id": second_id},
            ]}
        if name == "ExtractedEdges":
            return {"edges": [{
                "relation_type": "INTERESTED_IN",
                "source_entity_name": NODE_A,
                "target_entity_name": NODE_B,
                "fact": f"{NODE_A} 对 {NODE_B} 很感兴趣，认为定价合理",
                "valid_at": None,
                "invalid_at": None,
            }]}
        if name == "MissingFacts":
            return {"missing_facts": []}
        if name == "NodeResolutions":
            # 0.11.x 只保留出现在消解列表中的节点：duplicate_idx=-1
            # 表示"新实体，保留"，必须覆盖全部抽取节点；
            # name 会覆盖抽取名，需回填真实实体名
            return {"entity_resolutions": [
                {"id": i, "duplicate_idx": -1, "name": self._last_extracted_names[i]}
                for i in range(min(self._last_extracted_count, len(self._last_extracted_names)))
            ]}
        if name == "NodeDuplicate":
            return {"id": 0, "duplicate_idx": -1, "name": ""}
        if name == "EdgeDuplicate":
            return {"duplicate_fact_id": -1, "contradicted_facts": []}
        if name == "EdgeDates":
            return {"valid_at": None, "invalid_at": None}
        if name == "InvalidatedEdges":
            return {"contradicted_facts": []}
        if name == "UniqueFacts":
            return {"unique_facts": []}

        # 动态实体属性模型（EntityAttributes_xxx：summary 必填 + 本体属性）
        fields = getattr(response_model, "model_fields", {})
        out = {}
        for field_name in fields:
            out[field_name] = "冒烟摘要：消费者对耳机感兴趣" if field_name == "summary" else ""
        return out


class SmokeEmbedder(EmbedderClient):
    """确定性假 Embedding：按输入哈希生成 1024 维向量（余弦可比）。"""

    EMBED_DIM = 1024

    def _embed_one(self, text: str) -> List[float]:
        vector = []
        seed = hashlib.sha256(text.encode("utf-8")).digest()
        for i in range(self.EMBED_DIM):
            byte = seed[i % len(seed)]
            vector.append(((byte * (i + 7)) % 256) / 255.0 - 0.5)
        return vector

    async def create(self, input_data) -> List[float]:
        text = input_data[0] if isinstance(input_data, list) else input_data
        return self._embed_one(str(text))

    async def create_batch(self, input_data_list: List[str]) -> List[List[float]]:
        return [self._embed_one(str(t)) for t in input_data_list]


class SmokeCrossEncoder(CrossEncoderClient):
    """假重排器：按原始顺序给递减分数。"""

    async def rank(self, query: str, passages: List[str]) -> List[tuple]:
        return [(p, 0.9 - i * 0.1) for i, p in enumerate(passages)]


def build_store_with_fakes():
    """构造注入假客户端的 Graphiti，并接到 GraphitiStore。"""

    from graphiti_core import Graphiti

    from app.services.graph_store.graphiti_store import GraphitiStore

    graphiti = Graphiti(
        Config.NEO4J_URI,
        Config.NEO4J_USER,
        Config.NEO4J_PASSWORD,
        llm_client=SmokeLLMClient(),
        embedder=SmokeEmbedder(),
        cross_encoder=SmokeCrossEncoder(),
    )

    store = GraphitiStore()
    store._client = graphiti
    return store, graphiti


def main() -> int:
    errors = validate_neo4j_config()
    if errors:
        print("✗ 配置缺失:", "；".join(errors))
        return 1

    # 1. Neo4j 连接
    try:
        get_driver().verify_connectivity()
        print(f"✓ Neo4j 连接成功: {Config.NEO4J_URI}")
    except Exception as e:
        print(f"✗ Neo4j 连接失败: {e}")
        return 1

    store, graphiti = build_store_with_fakes()

    # 2. 索引与约束
    from app.utils.async_loop import run_async

    try:
        run_async(graphiti.build_indices_and_constraints(), timeout=120)
        print("✓ Graphiti 索引与约束就绪")
    except Exception as e:
        print(f"✗ 索引初始化失败: {e}")
        return 1

    try:
        # 3. 本体 → 自定义实体类型
        store.create_graph("smoke-full-loop")
        store.set_ontology(GRAPH_ID, {
            "entity_types": [
                {"name": "Consumer", "description": "A consumer",
                 "attributes": [{"name": "budget", "type": "text", "description": "预算"}]},
                {"name": "Product", "description": "A product", "attributes": []},
            ],
            "edge_types": [
                {"name": "INTERESTED_IN", "description": "interest",
                 "source_targets": [{"source": "Consumer", "target": "Product"}],
                 "attributes": []},
            ],
        })

        # 4. 摄取（真实抽取流水线 + 假 LLM）
        result = store.add_text_batches(
            GRAPH_ID,
            [
                f"张三是一名通勤白领，月预算3000元。{NODE_B}定价249元，主打降噪。{NODE_A}认为定价合理。",
                "（第二个文档块）张三计划在首销日下单。",
            ],
            progress_callback=lambda msg, prog: None,
        )
        print(f"✓ 摄取完成: {result.item_count} 个 episode")

        # 5. 落库枚举
        data = store.get_graph_data(GRAPH_ID)
        named = [n["name"] for n in data["nodes"] if n.get("name")]
        typed = [
            n for n in data["nodes"]
            if any(label != "Entity" for label in (n.get("labels") or []))
        ]
        print(f"✓ 图谱枚举: 节点 {data['node_count']} 个 {named[:4]}, 边 {data['edge_count']} 条")
        if data["node_count"] == 0:
            print("✗ 摄取后图谱为空")
            return 1
        if data["edge_count"] == 0:
            print("✗ 摄取后无边（边抽取流水线异常）")
            return 1
        if not named:
            print("✗ 节点缺少名称（实体名落库异常）")
            return 1
        if not typed:
            print("✗ 节点缺少自定义类型标签（本体→Neo4j 标签链路异常）")
            return 1

        # 6. 语义检索（假 embedding 余弦 + 全文）
        edge_search = store.search(GRAPH_ID, "对耳机感兴趣 定价", limit=5, scope="edges")
        print(f"✓ 边语义检索: {len(edge_search.edges)} 条")
        node_search = store.search(GRAPH_ID, NODE_A, limit=5, scope="nodes")
        print(f"✓ 节点检索: {len(node_search.nodes)} 个")
        if not node_search.nodes:
            print("✗ 节点检索无结果")
            return 1

        # 7. 模拟活动回写（add_episodes 路径）
        episode_uuids = store.add_episodes(
            GRAPH_ID,
            [f"[twitter round 1] {NODE_A}: 发布了一条帖子：「已下单，等发货」"],
            reference_time="2026-11-15T10:00:00+00:00",
            source_description="MiroFish simulation activity batch",
        )
        print(f"✓ 模拟活动回写: {len(episode_uuids)} 个 episode")

        # 8. 删除与隔离
        store.delete_graph(GRAPH_ID)
        leftover = run_query(
            "MATCH (n {group_id: $gid}) RETURN count(n) AS c",
            {"gid": GRAPH_ID},
            operation_name="verify cleanup",
        )
        remaining = leftover[0]["c"] if leftover else 0
        if remaining:
            print(f"✗ 删除后仍残留 {remaining} 个节点")
            return 1
        print("✓ 命名空间删除干净")

        print("\n✅ 全闭环冒烟通过（真 Neo4j + 假 LLM，全部代码路径已验证）")
        return 0

    except Exception as e:
        import traceback

        print(f"✗ 冒烟失败: {e}")
        traceback.print_exc()
        return 1
    finally:
        store.delete_graph(GRAPH_ID)


if __name__ == "__main__":
    sys.exit(main())
