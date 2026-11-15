# 电商新品上市预演 — 使用说明

基于 MiroFish 的多智能体模拟引擎，把"新品上市"这一商业事件投放到一个由
消费者、KOL、竞品、媒体等 Agent 组成的平行数字世界中，预演上市后的市场
反应，产出可指导定价、KOL 投放与上市节奏的决策依据。

## 0. 环境准备

图谱后端为 **Graphiti + Neo4j**（完全开源，不依赖 Zep Cloud）：

```bash
# 1. 配置 .env（参考 .env.example）
cp .env.example .env
#   LLM_API_KEY / LLM_BASE_URL / LLM_MODEL_NAME   —— 本体/人设/模拟/报告用
#   NEO4J_PASSWORD                                 —— Neo4j 密码
#   EMBEDDING_*                                    —— Graphiti 向量检索用
#      （阿里百炼 text-embedding-v4 或任意 OpenAI 兼容 embedding 端点；
#        缺省回退到 LLM_* 端点）

# 2. 启动 Neo4j（docker-compose 已内置）
docker compose up -d neo4j

# 3. 校验图谱链路（摄取→建图→检索闭环）
cd backend && uv run python scripts/validate_graphiti_integration.py
```

## 1. 预演流程（前端五步向导）

1. **首页**：选择场景卡片「电商新品上市预演」→ 上传产品资料/竞品分析/
   KOL 清单（PDF/MD/TXT）→ 可点击「填充电商模板」快速生成需求描述
   （含产品、定价、目标人群、竞品、上市计划、KOL 投放）→ 启动引擎。
2. **Step1 图谱构建**：LLM 按电商本体生成本体（发声主体 + Product/
   Promotion 知识节点），经 Graphiti 写入 Neo4j。
3. **Step2 环境搭建**：只有发声主体生成 Agent（**产品/价格是知识节点，
   不产生 Agent**，直接省掉这部分模拟成本）；电商场景默认 Agent 上限
   60，按 竞品→KOL→专家→媒体→品牌→消费者 优先级截断。
4. **Step3 仿真运行**：
   - round-0 自动注入 官宣帖/KOL 种草帖/媒体评测；
   - 模拟中途按时间线注入 **定时事件**（首销开售、竞品降价反击、口碑
     事件——由 LLM 生成的 `scheduled_events` 驱动）；
   - 顶部「市场指标」面板实时显示 声量/情绪/购买意愿 三条曲线与
     价格/购买/质量/竞品关键词热度（规则提取，零 LLM 成本）；
   - 「问卷探针」按钮可随时抽样 12 位消费者 Agent，收集购买意愿打分、
     心理价位与主要顾虑。
5. **Step4 报告**：ReportAgent 新增 `market_metrics` 工具，报告章节可
   引用真实指标数字；报告页右上角「**对比预演**」入口可创建 A/B 变体。

## 2. 对比预演（Campaign）

在报告页点击「对比预演」→ 编辑变体（改价格：把 `249` 替换为 `199`）→
「创建并运行」。变体通过**克隆基线模拟**生成（人设与配置直接复制，
**不产生 LLM 调用**），串行运行后自动聚合对比表：

| 变体 | 发帖 | 评论 | 情绪均值 | 购买意愿 |
|---|---|---|---|---|
| 基线 | 320 | 890 | +0.12 | 0.58 |
| Δ 定价199 | +45 | +130 | +0.21 | +0.17 |

再点「生成对比报告」获得 LLM 撰写的方案建议（单次 LLM 调用）。

## 3. 资源消耗控制（已内置）

| 措施 | 说明 |
|---|---|
| 知识节点过滤 | Product/Promotion 只进图谱，不生成 Agent |
| Agent 上限 | 电商场景默认 60 个 Agent（prepare 请求可用 `max_agents` 覆盖） |
| 指标分类 opt-in | 声量/关键词走规则提取（零成本）；LLM 情绪/购买意愿分类仅在显式请求或模拟结束时执行，单轮抽样上限 40 条，结果按内容哈希缓存 |
| 问卷探针 | 复用现有 IPC 采访机制，抽样 ≤20 人 |
| Campaign 变体 | 克隆不调 LLM；变体串行运行；变体不回写图谱（避免污染基线） |

## 4. 关键 API（后端直连时）

```
POST /api/graph/ontology/generate        # multipart，新增 scenario 字段（ecommerce）
POST /api/simulation/create              # scenario 自动从项目继承
POST /api/simulation/prepare             # 新增可选 max_agents
GET  /api/simulation/<id>/market-metrics # ?classify=true 启用 LLM 分类
POST /api/simulation/<id>/survey-probe   # {sample_size: 12}
POST /api/campaign/create                # {base_simulation_id, variants[]}
POST /api/campaign/<id>/run              # 串行运行
GET  /api/campaign/<id>/comparison       # 指标对比
POST /api/campaign/<id>/report           # LLM 对比报告
```

## 5. 兼容性说明

- 旧项目（Zep 时代）的图谱数据无法迁移，需在图谱构建页 force 重建到
  Neo4j；项目元数据（project.json）完全兼容。
- 默认场景 `public_opinion` 的全链路 prompt 与原版逐字一致（迁移自
  `app/scenarios/public_opinion.py`），舆情预演行为不变。
