"""真 LLM 图谱冒烟：真实 LLM 抽取（DeepSeek 等任意 OpenAI 兼容 chat 端点）
+ 确定性假 Embedding + 真实 Neo4j。

与 ``validate_graphiti_full_loop.py`` 的区别：LLM 换成真实调用，验证
抽取质量与真实端点兼容性（JSON 输出、max_tokens 上限、多语言）。

端点兼容（max_tokens 钳制、schema 镜像响应规范化）已内置到生产代码
``graphiti_store.CompatOpenAIGenericClient``，通过 ``LLM_MAX_OUTPUT_TOKENS``
配置钳制上限（DeepSeek=8192）。

为什么 Embedding 用假的：DeepSeek 不提供 embedding 接口，而 Graphiti
必须向量化节点/事实。真实部署时请配置一个 embedding 端点（百炼
text-embedding-v4 / Ollama bge-m3 等），见 .env.example 的 EMBEDDING_*。

用法：cd backend && uv run python scripts/validate_graphiti_llm.py
（需要 .env: LLM_API_KEY/LLM_BASE_URL/LLM_MODEL_NAME + NEO4J_PASSWORD）
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from graphiti_core import Graphiti
from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
from graphiti_core.llm_client.config import LLMConfig
from openai import AsyncOpenAI

from app.config import Config  # noqa: E402
from app.services.graph_store.neo4j_client import (  # noqa: E402
    get_driver,
    validate_neo4j_config,
)
from app.utils.async_loop import run_async  # noqa: E402

GRAPH_ID = "mirofish_llm_smoke"


def main() -> int:
    errors = validate_neo4j_config()
    llm_errors = []
    if not Config.LLM_API_KEY:
        llm_errors.append("LLM_API_KEY 未配置")
    if errors or llm_errors:
        print("✗ 配置缺失:", "；".join(errors + llm_errors))
        return 1

    print(f"端点: {Config.LLM_BASE_URL}  模型: {Config.LLM_MODEL_NAME}")
    print("Embedding: 使用确定性假向量（DeepSeek 无 embedding 接口；"
          "真实部署请配置 EMBEDDING_* 端点）\n")

    # 1. Neo4j 连接
    try:
        get_driver().verify_connectivity()
        print(f"✓ Neo4j 连接成功: {Config.NEO4J_URI}")
    except Exception as e:
        print(f"✗ Neo4j 连接失败: {e}")
        return 1

    # 2. 构建真 LLM 客户端的 Graphiti（走生产兼容层 CompatOpenAIGenericClient）
    llm_config = LLMConfig(
        api_key=Config.LLM_API_KEY or "",
        model=Config.LLM_MODEL_NAME,
        small_model=Config.LLM_MODEL_NAME,
        base_url=Config.LLM_BASE_URL,
    )
    from scripts.validate_graphiti_full_loop import SmokeEmbedder
    from app.services.graph_store.graphiti_store import CompatOpenAIGenericClient

    graphiti = Graphiti(
        Config.NEO4J_URI,
        Config.NEO4J_USER,
        Config.NEO4J_PASSWORD,
        llm_client=CompatOpenAIGenericClient(
            config=llm_config,
            max_output_tokens_limit=Config.LLM_MAX_OUTPUT_TOKENS,
        ),
        embedder=SmokeEmbedder(),
        cross_encoder=OpenAIRerankerClient(
            config=llm_config,
            client=AsyncOpenAI(
                api_key=Config.LLM_API_KEY or "",
                base_url=Config.LLM_BASE_URL,
            ),
        ),
    )
    from app.services.graph_store.graphiti_store import GraphitiStore

    store = GraphitiStore()
    store._client = graphiti

    try:
        run_async(graphiti.build_indices_and_constraints(), timeout=120)
        print("✓ Graphiti 索引与约束就绪\n")
    except Exception as e:
        print(f"✗ 索引初始化失败: {e}")
        return 1

    def report(msg, prog):
        print(f"  [{int(prog * 100):3d}%] {msg}")

    try:
        # 3. 本体 + 真实 LLM 摄取
        store.create_graph("smoke-llm")
        store.set_ontology(GRAPH_ID, {
            "entity_types": [
                {"name": "Consumer", "description": "A consumer/potential buyer",
                 "attributes": [{"name": "budget", "type": "text", "description": "monthly budget"}]},
                {"name": "Product", "description": "A product/single SKU",
                 "attributes": [{"name": "price", "type": "text", "description": "price point"}]},
            ],
            "edge_types": [
                {"name": "INTERESTED_IN", "description": "interest in a product",
                 "source_targets": [{"source": "Consumer", "target": "Product"}],
                 "attributes": []},
            ],
        })

        print("── 真实 LLM 摄取（每块约 8-12 次 LLM 调用）──")
        result = store.add_text_batches(
            GRAPH_ID,
            [
                "张三是一名28岁的通勤白领，月消费预算4000元。他最近看中了'星尘降噪耳机X'，"
                "定价599元，主打42dB主动降噪。他认为这个价格略贵但可以接受，打算等首销日有优惠再下单。",
                "'星尘降噪耳机X'的竞品是'悦耳AirPro'，定价499元。李四是一名数码博主，"
                "对比评测后认为星尘的降噪更强，但悦耳的佩戴更舒适。",
            ],
            progress_callback=report,
        )
        print(f"✓ 摄取完成: {result.item_count} 个 episode\n")

        # 4. 枚举与断言
        data = store.get_graph_data(GRAPH_ID)
        named = [(n["name"], [l for l in n["labels"] if l != "Entity"]) for n in data["nodes"]]
        print(f"✓ 实体 {data['node_count']} 个: {named}")
        facts = [e["fact"] for e in data["edges"]][:6]
        print(f"✓ 关系 {data['edge_count']} 条:")
        for fact in facts:
            print(f"    - {fact}")

        if data["node_count"] < 2:
            print("✗ 抽取实体过少")
            return 1
        if data["edge_count"] < 1:
            print("✗ 未抽取到关系")
            return 1
        typed = [n for n in named if n[1]]
        if not typed:
            print("✗ 没有实体被分类到自定义类型")
            return 1

        # 5. 语义检索
        edge_search = store.search(GRAPH_ID, "降噪耳机 价格 对比", limit=5, scope="edges")
        print(f"✓ 边语义检索: {len(edge_search.edges)} 条")
        for edge in edge_search.edges[:3]:
            print(f"    - {edge.fact}")
        node_search = store.search(GRAPH_ID, "消费者", limit=5, scope="nodes")
        print(f"✓ 节点检索: {len(node_search.nodes)} 个")

        # 6. 模拟活动回写（真实 LLM 抽取）
        store.add_episodes(
            GRAPH_ID,
            ["[twitter round 1] 张三: 发布了一条帖子：「星尘耳机X首销日下单了，希望物有所值」"],
            reference_time="2026-11-15T10:00:00+00:00",
            source_description="MiroFish simulation activity batch",
        )
        print("✓ 模拟活动回写完成（真实 LLM 抽取）")

        print("\n✅ 真 LLM 图谱冒烟通过")
        return 0

    except Exception as e:
        import traceback

        print(f"\n✗ 冒烟失败: {e}")
        traceback.print_exc()
        return 1
    finally:
        store.delete_graph(GRAPH_ID)


if __name__ == "__main__":
    sys.exit(main())
