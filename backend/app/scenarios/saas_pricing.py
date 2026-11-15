"""SaaS 定价/改版沙盘场景。

预演"定价调整/大版本改版"发布后 SaaS 用户的反应：付费用户接受度、
免费用户流失、竞品趁机截流、社区舆论（HN/Reddit/Twitter）。
"""

from .base import Scenario

ONTOLOGY_SYSTEM_PROMPT = """你是一个专业的知识图谱本体设计专家。你的任务是分析给定的文本内容和模拟需求，设计适合**SaaS 定价/改版沙盘模拟**的实体类型和关系类型。

**重要：你必须输出有效的JSON格式数据，不要输出任何其他内容。**

## 核心任务背景

我们正在构建一个**SaaS 定价/改版沙盘**。场景：SaaS 公司即将调整定价或发布重大改版，预演用户群体的反应。其中：
- 一部分实体是"发声主体"：免费用户、付费用户、流失用户、独立开发者社区、科技媒体、我方公司、竞品
- 另一部分实体是"知识节点"：定价方案、功能版本——它们是被讨论的对象，不发声

**不可以是**：抽象概念（"口碑"、"用户情绪"）、主题（"定价策略"）、观点（"支持方"）。

## 输出格式

请输出JSON格式，包含以下结构：

```json
{
    "entity_types": [{"name": "PascalCase英文", "description": "英文不超过100字符", "attributes": [{"name": "snake_case", "type": "text", "description": "属性描述"}], "examples": ["示例"]}],
    "edge_types": [{"name": "UPPER_SNAKE_CASE", "description": "英文不超过100字符", "source_targets": [{"source": "源", "target": "目标"}], "attributes": []}],
    "analysis_summary": "简要分析"
}
```

## 设计指南（极其重要！）

**数量要求：必须正好10个实体类型**，最后2个必须是兜底类型：

A. **兜底类型（最后2个）**：`Person`（自然人兜底）、`Organization`（组织兜底）

B. **具体类型（8个）**：必须覆盖发声主体与知识节点：
   - 发声主体示例：`SaaSUser`（在用用户）、`ChurnedUser`（已流失用户）、`IndieHackerKOL`（独立开发者社区意见领袖）、`TechMedia`（科技媒体）、`SaaSOfficial`（我方官方）、`CompetitorSaaS`（竞品公司）
   - 知识节点示例：`PricingPlan`（定价方案，属性含 monthly_price/annual_discount）、`FeatureRelease`（功能版本）

### 2. 关系类型设计（6-10个）
`SUBSCRIBES_TO`（订阅）、`CHURNED_FROM`（已流失）、`UPGRADES_TO`、`DISCUSSES`、`UNDERCUTS`、`SHIPS`（发布版本）、`REPORTS_ON`。

### 3. 属性设计
1-3个属性；禁用 `name/uuid/group_id/graph_id/created_at/summary`。
"""

ONTOLOGY_USER_RULES = """
请根据以上内容，设计适合 SaaS 定价/改版沙盘的实体类型和关系类型。

**必须遵守的规则**：
1. 正好10个实体类型；最后2个是 Person/Organization 兜底
2. 前8个必须同时覆盖发声主体（用户/社区KOL/媒体/双方公司）和知识节点（定价方案/功能版本）
3. 抽象概念不可以；定价方案与功能版本是合法知识节点
4. 属性名禁用系统保留字
"""

PERSONA_SYSTEM_PROMPT = "你是 SaaS 行业模拟专家，生成详细、真实的人物与账号设定用于定价/改版沙盘。必须返回有效的JSON格式，所有字符串值不能包含未转义的换行符。"

INDIVIDUAL_PERSONA_PROMPT = """为实体生成详细的社交媒体用户人设，用于 SaaS 定价/改版沙盘模拟。

实体名称: {entity_name}
实体类型: {entity_type}
实体摘要: {entity_summary}
实体属性: {attrs_str}

上下文信息:
{context_str}

请生成JSON，包含以下字段:

1. bio: 社交媒体简介，200字
2. persona: 详细人设描述（2000字的纯文本），需包含:
   - 基本信息（职业、团队规模、使用该 SaaS 的场景与时长、付费档位）
   - 使用特征（核心工作流、依赖的功能、月度工具预算、替代品有哪些）
   - 对定价/改版的态度（新价格对其 TCO 的影响、改版后工作流是否被打断、迁移成本评估）
   - 社区行为（在 HN/Reddit/Twitter/X 上的发言风格、活跃时段）
   - 个人记忆（这个个体与本次定价调整/改版事件的关联及已有反应）
3. age: 年龄数字（必须是整数）
4. gender: "male" 或 "female"
5. mbti: MBTI类型
6. country: 国家（使用中文）
7. profession: 职业
8. interested_topics: 感兴趣话题数组

重要:
- 所有字段值必须是字符串或数字，不要使用换行符
- persona必须是一段连贯的文字描述
- {language_instruction} (gender字段必须用英文male/female)
- age必须是有效的整数
"""

GROUP_PERSONA_PROMPT = """为机构实体生成详细的社交媒体账号设定，用于 SaaS 定价/改版沙盘模拟。

实体名称: {entity_name}
实体类型: {entity_type}
实体摘要: {entity_summary}
实体属性: {attrs_str}

上下文信息:
{context_str}

请生成JSON，包含以下字段:

1. bio: 官方账号简介，200字
2. persona: 详细账号设定描述（2000字的纯文本），需包含:
   - 机构基本信息（公司/媒体名称、定位、行业地位）
   - 账号定位（我方官方侧重定价沟通与安抚；竞品侧重截流营销；科技媒体侧重客观报道与行业分析）
   - 发言风格与发布内容特点
   - 立场态度（对本次定价调整的立场、面对用户流失质疑的应对方式）
   - 机构记忆（与本次事件的关联及已有动作）
3. age: 固定填30
4. gender: 固定填"other"
5. mbti: MBTI类型
6. country: 国家（使用中文）
7. profession: 机构职能描述
8. interested_topics: 关注领域数组

重要:
- 所有字段值必须是字符串或数字，不允许null值
- persona必须是一段连贯的文字描述，不要使用换行符
- {language_instruction} (gender字段必须用英文"other")
- 机构账号发言要符合其身份定位"""

INDIVIDUAL_ENTITY_TYPES = (
    "saasuser", "churneduser", "indiehackerkol", "person", "publicfigure",
)

GROUP_ENTITY_TYPES = (
    "techmedia", "saasofficial", "competitorsaas", "organization", "company",
)

KNOWLEDGE_NODE_TYPES = ("pricingplan", "featurerelease", "plan", "release")

AGENT_PRIORITY = (
    "competitorsaas", "indiehackerkol", "techmedia", "saasofficial",
    "publicfigure", "saasuser", "churneduser", "person", "organization", "company",
)

DEFAULT_MAX_AGENTS = 60

TIME_CONFIG_PROMPT = """基于以下 SaaS 定价/改版预演需求，生成时间模拟配置。

{context_truncated}

## 任务
请生成时间配置JSON。时间线覆盖：定价调整/改版公告 → 社区讨论发酵 → 用户流失或接受 → 竞品动作 → 定格。

### 开发者/科技从业者作息参考（UTC+8，可按目标市场调整）：
- 凌晨0-3点仍有活跃开发者（活跃度系数0.3——SaaS 用户常在深夜讨论工具）
- 早8-10点通勤+晨间资讯（活跃度系数0.6）
- 工作时间10-12、14-18点活跃（活跃度系数0.9——SaaS 讨论多在工作时间发生）
- 晚20-23点是 HN/Reddit/社区高峰（活跃度系数1.5）

### 返回JSON格式（不要markdown）

示例：
{{
    "total_simulation_hours": 72,
    "minutes_per_round": 60,
    "agents_per_hour_min": 5,
    "agents_per_hour_max": 50,
    "peak_hours": [10, 11, 15, 16, 20, 21, 22],
    "off_peak_hours": [3, 4, 5, 6],
    "morning_hours": [8, 9],
    "work_hours": [10, 11, 14, 15, 16, 17, 18],
    "reasoning": "针对该 SaaS 用户群体的时间配置说明"
}}

字段说明：
- total_simulation_hours (int): 48-96小时
- minutes_per_round (int): 建议60分钟
- agents_per_hour_min/max (int): 取值范围 1-{max_agents_allowed}
- peak_hours / off_peak_hours / morning_hours / work_hours (int数组)
- reasoning (string)"""

TIME_CONFIG_SYSTEM_PROMPT = "你是 SaaS 行业模拟专家。返回纯JSON格式，时间配置需符合开发者与科技从业者的作息习惯。"

DEFAULT_TIME_CONFIG = {
    "total_simulation_hours": 72,
    "minutes_per_round": 60,
    "peak_hours": [10, 11, 15, 16, 20, 21, 22],
    "off_peak_hours": [3, 4, 5, 6],
    "morning_hours": [8, 9],
    "work_hours": [10, 11, 14, 15, 16, 17, 18],
    "reasoning": "使用默认开发者社区作息配置（工作时间+晚间社区高峰）",
}

EVENT_CONFIG_PROMPT = """基于以下 SaaS 定价/改版预演需求，生成事件配置。

模拟需求: {simulation_requirement}

{context_truncated}

## 可用实体类型及示例
{type_info}

## 任务
请生成事件配置JSON，预演"公告 → 社区发酵 → 用户反应 → 竞品动作 → 定格"时间线：

1. 提取热点话题关键词（价格数字、功能名、竞品名、迁移词）
2. 描述社区舆论发展方向
3. 设计初始帖子（公告与第一波反应），**每个帖子必须指定 poster_type**：
   - 官方定价/改版公告（SaaSOfficial 类型）
   - 用户第一反应（SaaSUser 类型）
   - 社区讨论帖（IndieHackerKOL 类型）
   - 科技媒体报道（TechMedia 类型）
4. 设计中途定时事件 scheduled_events（社区发酵与竞品动作），每个事件必须指定 trigger_round（从1开始计数，0 保留）：
   - 社区深度讨论/HN 帖子发酵（trigger_round 建议在20%-40%）
   - 竞品截流营销（推出迁移优惠）（trigger_round 建议在40%-60%）
   - 我方让步/补偿方案（trigger_round 建议在50%-70%）
   - 用户分化定格（接受/流失案例）（trigger_round 建议80%之后）

返回JSON格式（不要markdown）：
{{
    "hot_topics": ["关键词1", ...],
    "narrative_direction": "<社区舆论发展方向>",
    "initial_posts": [
        {{"content": "帖子内容", "poster_type": "实体类型"}},
        ...
    ],
    "scheduled_events": [
        {{"content": "事件帖内容", "poster_type": "实体类型", "trigger_round": 10, "event_name": "竞品截流"}},
        ...
    ],
    "reasoning": "<简要说明>"
}}"""

EVENT_CONFIG_SYSTEM_PROMPT = "你是 SaaS 行业分析师。返回纯JSON格式。poster_type 必须精确匹配可用实体类型，scheduled_events 的 trigger_round 必须是正整数且从1开始。"

AGENT_CONFIG_PROMPT = """基于以下信息，为每个实体生成 SaaS 定价/改版模拟的活动配置。

模拟需求: {simulation_requirement}

## 实体列表
```json
{entity_list_json}
```

## 任务
为每个实体生成活动配置，注意：
- **时间符合开发者社区作息**：工作时间与晚间社区高峰
- **在用用户**（SaaSUser）：活跃度中高(0.5-0.8)，影响低(0.6-1.0)，立场取决于新定价对自身成本的影响
- **已流失用户**（ChurnedUser）：活跃度低(0.3-0.5)，倾向唱衰或已迁移，立场 opposing
- **社区KOL**（IndieHackerKOL）：活跃度高(0.6-0.85)，影响力高(1.8-2.5)，观点有分量
- **科技媒体**（TechMedia）：全天(8-23)，影响力高(2.0-2.5)，observer
- **我方官方**（SaaSOfficial）：工作时间+公告节点，影响力高(2.5-3.0)，supportive
- **竞品**（CompetitorSaaS）：活跃度低(0.2-0.4)，截流营销，影响力高(2.0-2.8)，opposing

返回JSON格式（不要markdown）：
{{
    "agent_configs": [
        {{
            "agent_id": <必须与输入一致>,
            "activity_level": <0.0-1.0>,
            "posts_per_hour": <发帖频率>,
            "comments_per_hour": <评论频率>,
            "active_hours": [<活跃小时列表>],
            "response_delay_min": <最小响应延迟分钟>,
            "response_delay_max": <最大响应延迟分钟>,
            "sentiment_bias": <-1.0到1.0>,
            "stance": "<supportive/opposing/neutral/observer>",
            "influence_weight": <影响力权重>
        }},
        ...
    ]
}}"""

AGENT_CONFIG_SYSTEM_PROMPT = "你是 SaaS 行业分析师。返回纯JSON，配置需符合各角色行为特征。"

RULE_AGENT_OFFICIAL = {
    "activity_level": 0.4, "posts_per_hour": 0.3, "comments_per_hour": 0.3,
    "active_hours": list(range(9, 22)), "response_delay_min": 15, "response_delay_max": 60,
    "sentiment_bias": 0.0, "stance": "supportive", "influence_weight": 2.8,
}
RULE_AGENT_USER = {
    "activity_level": 0.65, "posts_per_hour": 0.4, "comments_per_hour": 1.2,
    "active_hours": [8, 9, 10, 11, 14, 15, 20, 21, 22], "response_delay_min": 2,
    "response_delay_max": 20, "sentiment_bias": 0.0, "stance": "neutral", "influence_weight": 0.8,
}
RULE_AGENT_KOL = {
    "activity_level": 0.75, "posts_per_hour": 0.7, "comments_per_hour": 0.8,
    "active_hours": [10, 11, 14, 15, 20, 21, 22, 23], "response_delay_min": 10,
    "response_delay_max": 60, "sentiment_bias": 0.0, "stance": "neutral", "influence_weight": 2.0,
}
RULE_AGENT_MEDIA = {
    "activity_level": 0.5, "posts_per_hour": 0.8, "comments_per_hour": 0.3,
    "active_hours": list(range(8, 24)), "response_delay_min": 5, "response_delay_max": 30,
    "sentiment_bias": 0.0, "stance": "observer", "influence_weight": 2.2,
}
RULE_AGENT_COMPETITOR = {
    "activity_level": 0.3, "posts_per_hour": 0.2, "comments_per_hour": 0.1,
    "active_hours": list(range(9, 19)), "response_delay_min": 30, "response_delay_max": 120,
    "sentiment_bias": 0.0, "stance": "opposing", "influence_weight": 2.4,
}
RULE_AGENT_DEFAULT = {
    "activity_level": 0.6, "posts_per_hour": 0.4, "comments_per_hour": 1.0,
    "active_hours": [10, 11, 15, 20, 21, 22], "response_delay_min": 2,
    "response_delay_max": 30, "sentiment_bias": 0.0, "stance": "neutral", "influence_weight": 1.0,
}

TYPE_ALIASES = {
    "saasofficial": ["saasofficial", "company", "organization"],
    "competitorsaas": ["competitorsaas", "competitor", "company"],
    "saasuser": ["saasuser", "user", "person"],
    "churneduser": ["churneduser", "person"],
    "indiehackerkol": ["indiehackerkol", "kol", "influencer"],
    "techmedia": ["techmedia", "mediaoutlet", "media"],
    "pricingplan": ["pricingplan"],
}

METRIC_KEYWORDS = {
    "price": ["价格", "涨价", "降价", "定价", "涨价潮", "太贵", "per seat", "pricing", "expensive", "increase"],
    "churn": ["取消", "退订", "迁移", "替代品", "流失", "cancel", "churn", "migrate", "alternative"],
    "competitor": ["竞品", "对手", "替代", "vs", "相比", "open source", "self-host", "competitor"],
    "feature": ["改版", "新功能", "破坏性变更", " breaking", "UI", "改版后", "redesign"],
}

SURVEY_TEMPLATE = (
    "关于{product_name}的定价调整/改版：1) 你会续费/升级吗（1-5分）？"
    "2) 新定价对你的影响有多大？3) 你会考虑迁移到哪个替代品？请简短回答。"
)

SURVEY_TARGET_TYPES = ("saasuser", "churneduser", "person")

REPORT_PLAN_SUPPLEMENT = """

【本场景为「SaaS 定价/改版沙盘」】
模拟世界预演的是 SaaS 定价调整/重大改版发布后的用户反应。报告应回答：
1. 公告后社区的即时反应是什么？哪些用户群体最先表达不满或支持？
2. 流失风险量化：多少声音明确表示取消/迁移？他们转向哪些替代品？
3. 定价接受度：新价格结构被接受还是抵制？什么档位/方案呼声最高？
4. 竞品截流动作的效果如何？
5. 给出定价/沟通策略建议：如何让这次调整损失最小。
建议章节方向：社区反应与声量走势、流失风险与迁移去向、定价接受度分析、
竞品截流与应对、定价策略与沟通建议。"""

REPORT_SECTION_SUPPLEMENT = """

【SaaS 沙盘章节写作要求】
- 引用用户关于"取消/续费/迁移"的原始发言作为流失风险证据
- 如工具结果中包含 market_metrics，必须引用具体数字
- 竞品截流效果需引用真实讨论（用户提到替代品的帖子）
- 定价结论需区分用户群体（个人开发者/小团队/企业）的不同反应"""

CAMPAIGN_OVERRIDES_DOC = "支持的变量：新定价档位（如 $15→$25）、改版方案、竞品截流力度、我方补偿方案。"

SAAS_PRICING_SCENARIO = Scenario(
    name="saas_pricing",
    label_key="home.scenarioLabelSaasPricing",
    description_key="home.scenarioDescSaasPricing",
    ontology_system_prompt=ONTOLOGY_SYSTEM_PROMPT,
    ontology_user_rules=ONTOLOGY_USER_RULES,
    persona_system_prompt=PERSONA_SYSTEM_PROMPT,
    individual_persona_prompt=INDIVIDUAL_PERSONA_PROMPT,
    group_persona_prompt=GROUP_PERSONA_PROMPT,
    individual_entity_types=INDIVIDUAL_ENTITY_TYPES,
    group_entity_types=GROUP_ENTITY_TYPES,
    knowledge_node_types=KNOWLEDGE_NODE_TYPES,
    agent_priority=AGENT_PRIORITY,
    default_max_agents=60,
    time_config_prompt=TIME_CONFIG_PROMPT,
    time_config_system_prompt=TIME_CONFIG_SYSTEM_PROMPT,
    default_time_config=DEFAULT_TIME_CONFIG,
    event_config_prompt=EVENT_CONFIG_PROMPT,
    event_config_system_prompt=EVENT_CONFIG_SYSTEM_PROMPT,
    agent_config_prompt=AGENT_CONFIG_PROMPT,
    agent_config_system_prompt=AGENT_CONFIG_SYSTEM_PROMPT,
    rule_agent_configs=(
        (("saasofficial", "company", "organization"), RULE_AGENT_OFFICIAL),
        (("saasuser", "churneduser", "person"), RULE_AGENT_USER),
        (("indiehackerkol", "publicfigure"), RULE_AGENT_KOL),
        (("techmedia",), RULE_AGENT_MEDIA),
        (("competitorsaas",), RULE_AGENT_COMPETITOR),
    ),
    type_aliases=TYPE_ALIASES,
    scheduled_events_enabled=True,
    metric_keywords=METRIC_KEYWORDS,
    survey_template=SURVEY_TEMPLATE,
    survey_target_types=SURVEY_TARGET_TYPES,
    report_plan_supplement=REPORT_PLAN_SUPPLEMENT,
    report_section_supplement=REPORT_SECTION_SUPPLEMENT,
    campaign_overrides_doc=CAMPAIGN_OVERRIDES_DOC,
)
