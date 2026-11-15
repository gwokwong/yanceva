"""Graphiti + Neo4j 集成校验脚本（取代原 validate_zep_cloud_integration.py）。

验证：
1. Neo4j 连接与凭据
2. Graphiti 客户端构建与索引初始化
3. episode 摄取 → 节点/边枚举 → 语义检索 的最小闭环
4. 清理测试数据

用法：cd backend && uv run python scripts/validate_graphiti_integration.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Config  # noqa: E402
from app.services.graph_store.neo4j_client import (  # noqa: E402
    get_driver,
    run_query,
    validate_neo4j_config,
)
from app.utils.async_loop import run_async  # noqa: E402


def main() -> int:
    errors = validate_neo4j_config()
    if errors:
        print("✗ 配置缺失:", "；".join(errors))
        return 1
    print(f"✓ Neo4j 配置: {Config.NEO4J_URI}")

    # 1. 连接
    try:
        driver = get_driver()
        driver.verify_connectivity()
        print("✓ Neo4j 连接成功")
    except Exception as e:
        print(f"✗ Neo4j 连接失败: {e}")
        return 1

    # 2. Graphiti 客户端 + 索引
    from app.services.graph_store import get_graph_store

    graph_id = "mirofish_validate_selfcheck"
    store = get_graph_store()
    try:
        store.create_graph("integration-selfcheck")
        store.set_ontology(graph_id, {
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
        print("✓ Graphiti 客户端构建与索引初始化成功")
    except Exception as e:
        print(f"✗ Graphiti 初始化失败: {e}")
        return 1

    # 3. 摄取 + 枚举 + 检索闭环
    try:
        result = store.add_text_batches(
            graph_id,
            ["张三是一名通勤白领，月预算3000元，对降噪耳机X很感兴趣，觉得249元的定价合理。"],
            progress_callback=lambda msg, prog: None,
        )
        assert result.item_count == 1, result

        data = store.get_graph_data(graph_id)
        print(f"✓ 摄取完成: 节点 {data['node_count']}, 边 {data['edge_count']}")
        if data["node_count"] == 0:
            print("✗ 摄取后图谱为空（LLM 抽取可能失败，请检查 LLM_API_KEY）")
            return 1

        search = store.search(graph_id, "降噪耳机 定价", limit=5, scope="edges")
        print(f"✓ 语义检索返回 {len(search.edges)} 条边结果")

        node_search = store.search(graph_id, "张三", limit=5, scope="nodes")
        print(f"✓ 节点检索返回 {len(node_search.nodes)} 个节点")
    except Exception as e:
        print(f"✗ 集成闭环失败: {e}")
        return 1
    finally:
        # 4. 清理
        store.delete_graph(graph_id)
        run_query(
            "MATCH (n {group_id: $gid}) DETACH DELETE n",
            {"gid": graph_id},
            operation_name="cleanup",
        )
        print("✓ 测试数据已清理")

    print("\n全部校验通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
