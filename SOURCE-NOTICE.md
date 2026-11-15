# Yanceva — 基于 MiroFish 的商业预演平台

本项目基于 [MiroFish](https://github.com/666ghj/MiroFish)（AGPL-3.0）修改和扩展。

## 许可证

本项目遵循 **GNU Affero General Public License v3.0 (AGPL-3.0)**。
原始许可证全文见 [LICENSE](LICENSE) 文件，版权归 MiroFish 原作者所有。

本仓库是 MiroFish 的修改版本。根据 AGPL-3.0 第 13 条（远程网络交互），
本修改版本的**完整源代码**（含全部修改）通过本公开仓库提供：
https://github.com/<your-username>/<your-repo>

## 主要修改

相对上游 MiroFish 的主要变更：

1. 场景注册表（`backend/app/scenarios/`）：将硬编码的舆情场景抽象为可扩展的 7 个商业场景
2. 图谱后端（`backend/app/services/graph_store/`）：从 Zep Cloud 迁移到 Graphiti + Neo4j（自托管）
3. 市场信号层（`backend/app/services/market_metrics_service.py`）：新增量化指标提取
4. 订单系统与 Worker（`backend/app/models/order.py`、`backend/app/worker.py`）：商业化接单执行
5. 品牌（Yanceva）与前端门户（落地页、订单、支付、多语言）

## AGPL-3.0 合规要点（部署者须知）

- 通过网络提供服务时，必须向用户提供本修改版源码（含你的后续修改）
- 不得将本软件改为专有软件闭源分发
- 保留原始版权声明与本许可证声明
