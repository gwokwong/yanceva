"""竞品发布应对沙盘场景。

预演"竞品发布新品/降价"冲击下我方市场的反应：老用户动摇、观望买家流向、
渠道与媒体态度、我方应对动作（降价/发对比稿/推新功能）的效果。
"""

from .base import Scenario

ONTOLOGY_SYSTEM_PROMPT = """你是一个专业的知识图谱本体设计专家。你的任务是分析给定的文本内容和模拟需求，设计适合**竞品发布应对沙盘模拟**的实体类型和关系类型。

**重要：你必须输出有效的JSON格式数据，不要输出任何其他内容。**

## 核心任务背景

我们正在构建一个**竞品发布应对沙盘**。场景：竞争对手即将发布新品/宣布降价，我们要预演我方市场的反应并测试应对策略。其中：
- 一部分实体是"发声主体"：我方老用户、观望买家、竞品粉丝、KOL、媒体、我方品牌、竞品品牌
- 另一部分实体是"知识节点"：我方产品、竞品新品——它们是被讨论和对比的对象，不发声

## 输出格式

请输出JSON格式，包含以下结构：

```json
{
    "entity_types": [
        {"name": "实体类型名称（英文，PascalCase）", "description": "简短描述（英文，不超过100字符）", "attributes": [{"name": "属性名（英文，snake_case）", "type": "text", "description": "属性描述"}], "examples": ["示例1"]},
    ],
    "edge_types": [{"name": "关系类型名称（英文，UPPER_SNAKE_CASE）", "description": "简短描述（英文，不超过100字符）", "source_targets": [{"source": "源实体类型", "target": "目标实体类型"}], "attributes": []}],
    "analysis_summary": "对文本内容的简要分析说明"
}
```

## 设计指南（极其重要！）

**数量要求：必须正好10个实体类型**，最后2个必须是兜底类型：

A. **兜底类型（放在列表最后2个）**：
   - `Person`: 任何自然人个体的兜底类型
   - `Organization`: 任何组织机构的兜底类型

B. **具体类型（8个）**：必须覆盖发声主体与知识节点两类：
   - 发声主体示例：`OurConsumer`（我方老用户）、`ProspectiveBuyer`（观望买家）、`CompetitorFan`（竞品粉丝）、`KOLInfluencer`、`MediaOutlet`、`OurBrandOfficial`、`CompetitorBrand`
   - 知识节点示例：`OurProduct`（我方产品，属性含 price/launch_date）、`CompetitorProduct`（竞品新品）
   - 根据文本内容调整，但发声主体至少4-5个、知识节点至少1-2个

**不可以是**：抽象概念（"口碑"、"市场情绪"）、主题（"性价比"）、观点（"支持方"）。

### 2. 关系类型设计（6-10个）
反映竞品语境下的真实联系：`CURRENTLY_USES`（正在使用）、`CONSIDERING_SWITCH`（考虑转投）、`RECOMMENDS`、`LAUNCHES`（发布）、`UNDERCUTS`（降价针对）、`DEFENDS`（防守回应）、`REPORTS_ON`、`COMPARES_WITH`。

### 3. 属性设计
每个实体类型1-3个属性；属性名禁用 `name/uuid/group_id/graph_id/created_at/summary`。
"""

ONTOLOGY_USER_RULES = """
请根据以上内容，设计适合竞品发布应对沙盘的实体类型和关系类型。

**必须遵守的规则**：
1. 必须正好输出10个实体类型
2. 最后2个必须是兜底类型：Person（个人兜底）和 Organization（组织兜底）
3. 前8个根据文本设计，必须同时覆盖发声主体（我方用户/观望买家/KOL/媒体/双方品牌）和知识节点（我方产品/竞品新品）
4. 抽象概念不可以；产品是合法知识节点
5. 属性名不能使用系统保留字
"""

PERSONA_SYSTEM_PROMPT = "你是电商与消费市场模拟专家，生成详细、真实的人物与账号设定用于竞品发布应对沙盘。必须返回有效的JSON格式，所有字符串值不能包含未转义的换行符。"

INDIVIDUAL_PERSONA_PROMPT = """为实体生成详细的社交媒体用户人设，用于竞品发布应对沙盘模拟。

实体名称: {entity_name}
实体类型: {entity_type}
实体摘要: {entity_summary}
实体属性: {attrs_str}

上下文信息:
{context_str}

请生成JSON，包含以下字段:

1. bio: 社交媒体简介，200字
2. persona: 详细人设描述（2000字的纯文本），需包含:
   - 基本信息（年龄、职业、收入水平、所在城市）
   - 消费特征（预算、常用平台、决策风格：理性比价/冲动种草/品牌忠诚/尝鲜）
   - 品牌关系（当前用什么产品、为什么、换品牌的门槛）
   - 对竞品发布的态度（心动点是什么：价格？功能？以及什么样的应对能留住/吸引他们）
   - 社交媒体行为（活跃时段、发帖频率、互动风格、语言特点）
   - 个人记忆（这个个体与本次竞品发布事件的关联及已有反应）
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

GROUP_PERSONA_PROMPT = """为机构/品牌实体生成详细的社交媒体账号设定，用于竞品发布应对沙盘模拟。

实体名称: {entity_name}
实体类型: {entity_type}
实体摘要: {entity_summary}
实体属性: {attrs_str}

上下文信息:
{context_str}

请生成JSON，包含以下字段:

1. bio: 官方账号简介，200字，专业得体
2. persona: 详细账号设定描述（2000字的纯文本），需包含:
   - 机构基本信息（名称、性质、行业地位）
   - 账号定位（我方品牌侧重新品防守与用户沟通；竞品侧重进攻性营销；媒体侧重客观对比报道）
   - 发言风格（语言特点、常用表达、禁忌话题）
   - 发布内容特点（内容类型、频率、活跃时段）
   - 立场态度（对本次竞品发布的立场、面对用户流失质疑的应对方式）
   - 机构记忆（这个机构与本次竞品发布事件的关联及已有动作）
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
    "ourconsumer", "prospectivebuyer", "competitorfan", "person",
    "publicfigure", "expert", "influencer",
)

GROUP_ENTITY_TYPES = (
    "ourbrandofficial", "mediaoutlet", "competitorbrand", "organization",
    "company", "channel",
)

KNOWLEDGE_NODE_TYPES = ("ourproduct", "competitorproduct", "product", "launch")

AGENT_PRIORITY = (
    "kolinfluencer", "mediaoutlet", "ourbrandofficial", "competitorbrand",
    "influencer", "publicfigure", "expert", "ourconsumer", "prospectivebuyer",
    "competitorfan", "person", "organization", "company", "channel",
)

DEFAULT_MAX_AGENTS = 60

TIME_CONFIG_PROMPT = """基于以下竞品发布应对预演需求，生成时间模拟配置。

{context_truncated}

## 任务
请生成时间配置JSON。时间线需要覆盖竞品发布冲击的完整节奏：竞品预热/官宣 → 市场震动 → 我方应对 → 用户回流或流失定格。

### 电商场景作息参考（东八区，可按目标人群调整）：
- 凌晨0-6点几乎无人活动（活跃度系数0.05）
- 早7-9点通勤刷手机渐活跃（活跃度系数0.4）
- 午12-13点午休高峰（活跃度系数1.1）
- 工作时段9-12、14-18点中等活跃（活跃度系数0.6）
- 晚19-23点是讨论、比价、下单高峰（活跃度系数1.5）
- 竞品官宣当日应显著放大活跃度；我方应对动作后有一波讨论回落

### 返回JSON格式（不要markdown）

示例：
{{
    "total_simulation_hours": 72,
    "minutes_per_round": 60,
    "agents_per_hour_min": 5,
    "agents_per_hour_max": 50,
    "peak_hours": [12, 13, 19, 20, 21, 22],
    "off_peak_hours": [0, 1, 2, 3, 4, 5],
    "morning_hours": [7, 8, 9],
    "work_hours": [9, 10, 11, 14, 15, 16, 17, 18],
    "reasoning": "针对该竞品发布节奏的时间配置说明"
}}

字段说明：
- total_simulation_hours (int): 模拟总时长，48-96小时
- minutes_per_round (int): 每轮时长，30-120分钟，建议60分钟
- agents_per_hour_min (int): 每小时最少激活Agent数（取值范围: 1-{max_agents_allowed}）
- agents_per_hour_max (int): 每小时最多激活Agent数（取值范围: 1-{max_agents_allowed}）
- peak_hours / off_peak_hours / morning_hours / work_hours (int数组)
- reasoning (string): 简要说明"""

TIME_CONFIG_SYSTEM_PROMPT = "你是电商市场模拟专家。返回纯JSON格式，时间配置需符合竞品发布节奏与目标消费群体作息。"

DEFAULT_TIME_CONFIG = {
    "total_simulation_hours": 72,
    "minutes_per_round": 60,
    "peak_hours": [12, 13, 19, 20, 21, 22],
    "off_peak_hours": [0, 1, 2, 3, 4, 5],
    "morning_hours": [7, 8, 9],
    "work_hours": [9, 10, 11, 14, 15, 16, 17, 18],
    "reasoning": "使用默认竞品发布节奏配置（午休+晚间高峰）",
}

EVENT_CONFIG_PROMPT = """基于以下竞品发布应对预演需求，生成事件配置。

模拟需求: {simulation_requirement}

{context_truncated}

## 可用实体类型及示例
{type_info}

## 任务
请生成事件配置JSON，预演"竞品官宣 → 市场震动 → 我方应对 → 结果定格"时间线：

1. 提取热点话题关键词（双方产品名、价格、对比词）
2. 描述市场舆论发展方向
3. 设计初始帖子（竞品官宣与第一波反应），**每个帖子必须指定 poster_type**：
   - 竞品官宣帖（CompetitorBrand 类型）
   - 我方用户动摇帖（OurConsumer 类型）
   - 媒体快讯（MediaOutlet 类型）
   - KOL 第一时间对比（KOLInfluencer 类型）
4. 设计中途定时事件 scheduled_events（我方应对动作与后续发酵），每个事件必须指定 trigger_round（从1开始计数，0 保留给初始事件）：
   - 我方应对动作：降价/发对比稿/推新功能/官宣升级（trigger_round 建议在总轮次的30%-50%）
   - 市场二次发酵：KOL 跟进对比、用户晒单回流（trigger_round 建议在60%-80%）

**重要**: poster_type 必须从"可用实体类型"中选择。

返回JSON格式（不要markdown）：
{{
    "hot_topics": ["关键词1", ...],
    "narrative_direction": "<市场舆论发展方向描述>",
    "initial_posts": [
        {{"content": "帖子内容", "poster_type": "实体类型"}},
        ...
    ],
    "scheduled_events": [
        {{"content": "事件帖内容", "poster_type": "实体类型", "trigger_round": 12, "event_name": "我方降价应对"}},
        ...
    ],
    "reasoning": "<简要说明>"
}}"""

EVENT_CONFIG_SYSTEM_PROMPT = "你是电商市场分析专家。返回纯JSON格式。poster_type 必须精确匹配可用实体类型，scheduled_events 的 trigger_round 必须是正整数且从1开始。"

AGENT_CONFIG_PROMPT = """基于以下信息，为每个实体生成竞品发布应对模拟的活动配置。

模拟需求: {simulation_requirement}

## 实体列表
```json
{entity_list_json}
```

## 任务
为每个实体生成活动配置，注意：
- **时间符合电商场景作息**：午休与晚间是消费讨论高峰
- **我方老用户**（OurConsumer）：活跃度中高(0.5-0.8)，午休+晚间，响应快(1-15分钟)，影响力低(0.6-1.0)，立场取决于对竞品的心动程度
- **观望买家**（ProspectiveBuyer）：活跃度高(0.6-0.85)，正在比价，提问多
- **竞品粉丝**（CompetitorFan）：活跃度高(0.6-0.8)，进攻性宣传竞品，立场 opposing
- **KOL**（KOLInfluencer）：活跃度高(0.6-0.85)，午休+晚间，影响力高(1.8-2.5)
- **我方品牌**（OurBrandOfficial）：活跃度中低(0.3-0.5)，工作时间+官宣节点活跃，影响力高(2.5-3.0)，立场 supportive
- **竞品品牌**（CompetitorBrand）：活跃度低(0.2-0.4)，工作时间，影响力高(2.0-2.8)，立场 opposing
- **媒体**（MediaOutlet）：全天活动(8-23)，影响力高(2.0-2.5)，立场 observer

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

AGENT_CONFIG_SYSTEM_PROMPT = "你是电商消费者行为分析专家。返回纯JSON，配置需符合竞品发布场景中各角色的行为特征。"

RULE_AGENT_BRAND = {
    "activity_level": 0.4, "posts_per_hour": 0.3, "comments_per_hour": 0.2,
    "active_hours": list(range(9, 22)), "response_delay_min": 15, "response_delay_max": 60,
    "sentiment_bias": 0.0, "stance": "supportive", "influence_weight": 2.8,
}
RULE_AGENT_KOL = {
    "activity_level": 0.75, "posts_per_hour": 0.7, "comments_per_hour": 0.8,
    "active_hours": [12, 13, 19, 20, 21, 22, 23], "response_delay_min": 10,
    "response_delay_max": 60, "sentiment_bias": 0.0, "stance": "neutral", "influence_weight": 2.0,
}
RULE_AGENT_CONSUMER = {
    "activity_level": 0.65, "posts_per_hour": 0.4, "comments_per_hour": 1.2,
    "active_hours": [7, 8, 12, 13, 19, 20, 21, 22, 23], "response_delay_min": 1,
    "response_delay_max": 15, "sentiment_bias": 0.0, "stance": "neutral", "influence_weight": 0.8,
}
RULE_AGENT_COMPETITOR = {
    "activity_level": 0.3, "posts_per_hour": 0.2, "comments_per_hour": 0.1,
    "active_hours": list(range(9, 18)), "response_delay_min": 30, "response_delay_max": 120,
    "sentiment_bias": 0.0, "stance": "opposing", "influence_weight": 2.4,
}
RULE_AGENT_MEDIA = {
    "activity_level": 0.5, "posts_per_hour": 0.8, "comments_per_hour": 0.3,
    "active_hours": list(range(8, 24)), "response_delay_min": 5, "response_delay_max": 30,
    "sentiment_bias": 0.0, "stance": "observer", "influence_weight": 2.2,
}
RULE_AGENT_EXPERT = {
    "activity_level": 0.4, "posts_per_hour": 0.3, "comments_per_hour": 0.5,
    "active_hours": list(range(9, 23)), "response_delay_min": 15, "response_delay_max": 90,
    "sentiment_bias": 0.0, "stance": "neutral", "influence_weight": 1.8,
}
RULE_AGENT_DEFAULT = {
    "activity_level": 0.6, "posts_per_hour": 0.4, "comments_per_hour": 1.0,
    "active_hours": [12, 13, 19, 20, 21, 22, 23], "response_delay_min": 2,
    "response_delay_max": 30, "sentiment_bias": 0.0, "stance": "neutral", "influence_weight": 1.0,
}

TYPE_ALIASES = {
    "ourbrandofficial": ["ourbrandofficial", "brand", "company", "organization"],
    "competitorbrand": ["competitorbrand", "competitor", "rival", "company"],
    "ourconsumer": ["ourconsumer", "consumer", "person", "user"],
    "prospectivebuyer": ["prospectivebuyer", "buyer", "person", "customer"],
    "competitorfan": ["competitorfan", "fan", "person"],
    "kolinfluencer": ["kolinfluencer", "kol", "influencer", "blogger"],
    "mediaoutlet": ["mediaoutlet", "media"],
    "channel": ["channel", "merchant", "organization"],
    "product": ["product"],
}

METRIC_KEYWORDS = {
    "price": ["价格", "定价", "贵", "便宜", "性价比", "降价", "优惠", "折扣", "price", "discount"],
    "switch": ["转投", "换", "迁移", "改用", "叛变", "回流", "switch", "move to"],
    "competitor": ["竞品", "对手", "对比", "吊打", "不如", "碾压", "同期", "vs", "competitor"],
    "loyalty": ["老用户", "忠实", "信仰", "情怀", "不再", "失望", "loyal", "disappointed"],
}

SURVEY_TEMPLATE = (
    "竞品刚发布了新产品/降价：你还会继续选择{product_name}吗？"
    "1) 留下/转向竞品/观望（三选一）；2) 什么条件下你会留下？3) 什么会推动你转投？请简短回答。"
)

SURVEY_TARGET_TYPES = ("ourconsumer", "prospectivebuyer", "person")

REPORT_PLAN_SUPPLEMENT = """

【本场景为「竞品发布应对沙盘」】
模拟世界预演的是"竞品发布新品/降价"冲击下我方市场的反应。报告应回答：
1. 竞品官宣后，声量与情绪如何变化？哪类用户最先动摇？
2. 流失风险有多大？用户转向竞品的真实理由是什么（价格/功能/信任）？
3. 我方应对动作（降价/对比稿/功能升级）是否有效挽回了用户？
4. KOL 与媒体的态度是帮了我方还是助推了竞品？
5. 给出应对策略的明确结论：哪种动作组合损失最小。
建议章节方向：竞品冲击波与声量走势、用户流失与留存分析、我方应对动作效果评估、
舆论攻防与KOL态度、应对策略建议。"""

REPORT_SECTION_SUPPLEMENT = """

【竞品应对沙盘章节写作要求】
- 引用用户关于"要不要换品牌"的原始发言作为流失/留存证据
- 如工具结果中包含 market_metrics（市场指标），必须引用具体数字
- 应对动作的效果要看用户实际反应（回流帖/继续动摇帖），而非仅看官方表态
- 竞品相关结论需引用真实对比讨论"""

CAMPAIGN_OVERRIDES_DOC = "支持的变量：我方应对策略（降价幅度/对比稿/功能升级）、应对时机（提前/延后）、竞品定价。"

COMPETITOR_RESPONSE_SCENARIO = Scenario(
    name="competitor_response",
    label_key="home.scenarioLabelCompetitorResponse",
    description_key="home.scenarioDescCompetitorResponse",
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
        (("ourbrandofficial", "company", "organization"), RULE_AGENT_BRAND),
        (("kolinfluencer", "influencer", "publicfigure"), RULE_AGENT_KOL),
        (("ourconsumer", "prospectivebuyer", "competitorfan", "customer", "person"), RULE_AGENT_CONSUMER),
        (("competitorbrand",), RULE_AGENT_COMPETITOR),
        (("mediaoutlet",), RULE_AGENT_MEDIA),
        (("expert",), RULE_AGENT_EXPERT),
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
