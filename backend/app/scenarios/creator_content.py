"""创作者内容风险预演场景。

预演创作者（YouTuber/TikTok/B站/Newsletter）发布内容后的受众反应：
掉粉风险、争议点、品牌方敏感点、替代表达建议。
"""

from .base import Scenario

ONTOLOGY_SYSTEM_PROMPT = """你是一个专业的知识图谱本体设计专家。你的任务是分析给定的文本内容和模拟需求，设计适合**创作者内容风险预演模拟**的实体类型和关系类型。

**重要：你必须输出有效的JSON格式数据，不要输出任何其他内容。**

## 核心任务背景

我们正在构建一个**创作者内容风险预演沙盘**。场景：创作者即将发布一期内容（视频/图文/Newsletter），预演发布后受众反应。其中：
- 一部分实体是"发声主体"：铁粉、路人观众、潜在批评者、品牌赞助方、同类创作者
- 另一部分实体是"知识节点"：内容作品、话题标签——它们是被讨论的对象

**不可以是**：抽象概念（"口碑"、"热度"）、主题（"内容质量"）、观点（"支持方"）。

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
   - 发声主体示例：`LoyalFan`（铁粉）、`CasualViewer`（路人观众）、`CriticHater`（批评者/黑粉）、`FellowCreator`（同类创作者）、`BrandSponsor`（品牌赞助方）、`PlatformModerator`（平台审核）
   - 知识节点示例：`ContentPiece`（内容作品，属性含 topic/format）、`SponsorDeal`（赞助合作）

### 2. 关系类型设计（6-10个）
`FOLLOWS`（关注）、`UNFOLLOWS`（取关）、`CRITICIZES`（批评）、`DEFENDS`（维护）、`SPONSORS`、`REACTS_TO`、`REPORTS`（举报/审核）、`COLLABS_WITH`。

### 3. 属性设计
1-3个属性；禁用 `name/uuid/group_id/graph_id/created_at/summary`。
"""

ONTOLOGY_USER_RULES = """
请根据以上内容，设计适合创作者内容风险预演的实体类型和关系类型。

**必须遵守的规则**：
1. 正好10个实体类型；最后2个是 Person/Organization 兜底
2. 前8个必须覆盖发声主体（粉丝/路人/批评者/品牌方/同类创作者/平台）和知识节点（内容/赞助）
3. 抽象概念不可以；内容作品是合法知识节点
4. 属性名禁用系统保留字
"""

PERSONA_SYSTEM_PROMPT = "你是创作者经济与社交媒体模拟专家，生成详细、真实的人物与账号设定用于内容风险预演。必须返回有效的JSON格式，所有字符串值不能包含未转义的换行符。"

INDIVIDUAL_PERSONA_PROMPT = """为实体生成详细的社交媒体用户人设，用于创作者内容风险预演。

实体名称: {entity_name}
实体类型: {entity_type}
实体摘要: {entity_summary}
实体属性: {attrs_str}

上下文信息:
{context_str}

请生成JSON，包含以下字段:

1. bio: 社交媒体简介，200字
2. persona: 详细人设描述（2000字的纯文本），需包含:
   - 基本信息（年龄、职业、关注该创作者多久、互动深度）
   - 观看动机（喜欢什么内容风格、为什么关注、会为什么取关）
   - 敏感点（什么话题/表达/立场会让TA不适或反感；对赞助内容的容忍度）
   - 社区行为（评论风格、活跃时段、是否弹幕/二创/转发）
   - 对本期的态度（期待什么、担心什么、基于摘要的初始立场）
   - 个人记忆（与该创作者和本期内容话题的关联）
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

GROUP_PERSONA_PROMPT = """为品牌方/机构实体生成详细的账号设定，用于创作者内容风险预演。

实体名称: {entity_name}
实体类型: {entity_type}
实体摘要: {entity_summary}
实体属性: {attrs_str}

上下文信息:
{context_str}

请生成JSON，包含以下字段:

1. bio: 账号简介，200字
2. persona: 详细账号设定描述（2000字的纯文本），需包含:
   - 机构基本信息（品牌/平台名称、定位）
   - 账号定位（品牌赞助方：关注内容调性是否与品牌安全相符、对争议内容的容忍度、撤资红线；平台审核：社区规则红线）
   - 发言风格与发布内容特点
   - 立场态度（对本期内容的立场、可能采取的动作）
   - 机构记忆（与该创作者及本期话题的关联）
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
    "loyalfan", "casualviewer", "critichater", "fellowcreator", "person", "publicfigure",
)

GROUP_ENTITY_TYPES = (
    "brandsponsor", "platformmoderator", "mediaoutlet", "organization", "company",
)

KNOWLEDGE_NODE_TYPES = ("contentpiece", "topic", "sponsordeal")

AGENT_PRIORITY = (
    "critichater", "brandsponsor", "fellowcreator", "loyalfan",
    "casualviewer", "platformmoderator", "publicfigure", "person", "organization",
)

DEFAULT_MAX_AGENTS = 60

TIME_CONFIG_PROMPT = """基于以下创作者内容风险预演需求，生成时间模拟配置。

{context_truncated}

## 任务
请生成时间配置JSON。时间线覆盖：内容发布 → 首波反应 → 争议发酵/传播 → 品牌方/平台动作 → 舆情定格。

### 观众作息参考（东八区，可按受众调整）：
- 凌晨0-5点低活跃（系数0.05）；午12-13点碎片刷（系数1.0）
- 晚18-24点是观看与评论高峰（系数1.5）；周末全天偏高

### 返回JSON格式（不要markdown）

示例：
{{
    "total_simulation_hours": 72,
    "minutes_per_round": 60,
    "agents_per_hour_min": 5,
    "agents_per_hour_max": 50,
    "peak_hours": [12, 13, 19, 20, 21, 22, 23],
    "off_peak_hours": [1, 2, 3, 4, 5],
    "morning_hours": [7, 8],
    "work_hours": [9, 10, 11, 14, 15, 16, 17, 18],
    "reasoning": "针对该内容发布节奏的配置说明"
}}

字段说明：
- total_simulation_hours (int): 48-96小时
- minutes_per_round (int): 建议60分钟
- agents_per_hour_min/max (int): 取值范围 1-{max_agents_allowed}
- peak_hours / off_peak_hours / morning_hours / work_hours (int数组)
- reasoning (string)"""

TIME_CONFIG_SYSTEM_PROMPT = "你是创作者经济与社交媒体模拟专家。返回纯JSON格式，时间配置需符合观众作息。"

DEFAULT_TIME_CONFIG = {
    "total_simulation_hours": 72,
    "minutes_per_round": 60,
    "peak_hours": [12, 13, 19, 20, 21, 22, 23],
    "off_peak_hours": [1, 2, 3, 4, 5],
    "morning_hours": [7, 8],
    "work_hours": [9, 10, 11, 14, 15, 16, 17, 18],
    "reasoning": "使用默认观众作息配置（晚间观看高峰）",
}

EVENT_CONFIG_PROMPT = """基于以下创作者内容风险预演需求，生成事件配置。

模拟需求: {simulation_requirement}

{context_truncated}

## 可用实体类型及示例
{type_info}

## 任务
请生成事件配置JSON，预演"发布 → 反应 → 争议发酵 → 定格"时间线：

1. 提取热点话题关键词（内容主题、争议词、创作者名）
2. 描述舆情发展方向
3. 设计初始帖子（发布与首波反应），**每个帖子必须指定 poster_type**：
   - 发布公告（创作者本人若在可用类型中，否则由 LoyalFan 转发形式）
   - 铁粉好评（LoyalFan 类型）
   - 路人评价（CasualViewer 类型）
   - 批评者的第一波质疑（CriticHater 类型）
4. 设计中途定时事件 scheduled_events（发酵与动作），每个事件必须指定 trigger_round（从1开始计数，0 保留）：
   - 争议发酵/二创传播（trigger_round 建议20%-40%）
   - 品牌方关注/平台审核动作（trigger_round 建议40%-70%）
   - 创作者回应或删改内容（trigger_round 建议50%-80%）
   - 舆情定格/掉粉定格（trigger_round 建议80%之后）

**重要**: poster_type 必须从"可用实体类型"中选择。

返回JSON格式（不要markdown）：
{{
    "hot_topics": ["关键词1", ...],
    "narrative_direction": "<舆情发展方向>",
    "initial_posts": [
        {{"content": "帖子内容", "poster_type": "实体类型"}},
        ...
    ],
    "scheduled_events": [
        {{"content": "事件帖内容", "poster_type": "实体类型", "trigger_round": 10, "event_name": "争议发酵"}},
        ...
    ],
    "reasoning": "<简要说明>"
}}"""

EVENT_CONFIG_SYSTEM_PROMPT = "你是社交媒体舆情分析专家。返回纯JSON格式。poster_type 必须精确匹配可用实体类型，scheduled_events 的 trigger_round 必须是正整数且从1开始。"

AGENT_CONFIG_PROMPT = """基于以下信息，为每个实体生成创作者内容风险模拟的活动配置。

模拟需求: {simulation_requirement}

## 实体列表
```json
{entity_list_json}
```

## 任务
为每个实体生成活动配置，注意：
- **时间符合观众作息**：午休碎片时间与晚间观看高峰
- **铁粉**（LoyalFan）：活跃度高(0.7-0.9)，第一时间维护创作者，影响力低(0.6-1.0)，supportive
- **路人**（CasualViewer）：活跃度中(0.4-0.7)，随看随评，influence 低
- **批评者/黑粉**（CriticHater）：活跃度高(0.6-0.85)，聚焦争议点攻击，opposing
- **品牌赞助方**（BrandSponsor）：活跃度低(0.2-0.3)，观察为主，关键时刻发声，影响力高(2.5-3.5)
- **同类创作者**（FellowCreator）：活跃度中(0.4-0.6)，观点专业有分量，影响力中高(1.5-2.0)
- **平台审核**（PlatformModerator）：活跃度低(0.1-0.2)，仅在争议升级时动作，影响力高(3.0)

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

AGENT_CONFIG_SYSTEM_PROMPT = "你是创作者经济分析师。返回纯JSON，配置需符合各角色行为特征。"

RULE_AGENT_FAN = {
    "activity_level": 0.8, "posts_per_hour": 0.5, "comments_per_hour": 1.5,
    "active_hours": [12, 13, 19, 20, 21, 22, 23], "response_delay_min": 1,
    "response_delay_max": 10, "sentiment_bias": 0.3, "stance": "supportive", "influence_weight": 0.8,
}
RULE_AGENT_VIEWER = {
    "activity_level": 0.55, "posts_per_hour": 0.3, "comments_per_hour": 1.0,
    "active_hours": [12, 19, 20, 21, 22], "response_delay_min": 2,
    "response_delay_max": 30, "sentiment_bias": 0.0, "stance": "neutral", "influence_weight": 0.7,
}
RULE_AGENT_CRITIC = {
    "activity_level": 0.75, "posts_per_hour": 0.6, "comments_per_hour": 1.3,
    "active_hours": [19, 20, 21, 22, 23], "response_delay_min": 1,
    "response_delay_max": 15, "sentiment_bias": -0.4, "stance": "opposing", "influence_weight": 1.0,
}
RULE_AGENT_SPONSOR = {
    "activity_level": 0.2, "posts_per_hour": 0.1, "comments_per_hour": 0.05,
    "active_hours": list(range(9, 18)), "response_delay_min": 60, "response_delay_max": 240,
    "sentiment_bias": 0.0, "stance": "observer", "influence_weight": 3.0,
}
RULE_AGENT_CREATOR = {
    "activity_level": 0.5, "posts_per_hour": 0.5, "comments_per_hour": 0.6,
    "active_hours": [14, 15, 19, 20, 21], "response_delay_min": 5,
    "response_delay_max": 45, "sentiment_bias": 0.0, "stance": "neutral", "influence_weight": 1.8,
}
RULE_AGENT_MODERATOR = {
    "activity_level": 0.15, "posts_per_hour": 0.05, "comments_per_hour": 0.05,
    "active_hours": list(range(9, 21)), "response_delay_min": 120, "response_delay_max": 480,
    "sentiment_bias": 0.0, "stance": "observer", "influence_weight": 3.0,
}
RULE_AGENT_DEFAULT = {
    "activity_level": 0.55, "posts_per_hour": 0.3, "comments_per_hour": 1.0,
    "active_hours": [12, 19, 20, 21, 22], "response_delay_min": 2,
    "response_delay_max": 30, "sentiment_bias": 0.0, "stance": "neutral", "influence_weight": 1.0,
}

TYPE_ALIASES = {
    "loyalfan": ["loyalfan", "fan", "person"],
    "casualviewer": ["casualviewer", "viewer", "person"],
    "critichater": ["critichater", "critic", "hater", "person"],
    "brandsponsor": ["brandsponsor", "sponsor", "brand", "organization"],
    "fellowcreator": ["fellowcreator", "creator", "person"],
    "platformmoderator": ["platformmoderator", "moderator", "organization"],
    "contentpiece": ["contentpiece"],
}

METRIC_KEYWORDS = {
    "churn": ["取关", "掉粉", "取消化订阅", "退订", "不看", "unfollow", "unsubscribe", "lost a sub"],
    "controversy": ["争议", "翻车", "立场", "带货", "恰饭", "双标", "不当言论", "apologize", "drama"],
    "sponsor_risk": ["品牌方", "赞助商", "撤资", "解约", "广告主", "brand safe", "sponsor"],
    "support": ["支持", "力挺", "没毛病", "继续更", "defend", "support"],
}

SURVEY_TEMPLATE = (
    "关于创作者发布的这期内容《{product_name}》：1) 你会继续关注吗（1-5分，5=继续）？"
    "2) 内容里有没有让你不适的点？3) 你对创作者有什么建议？请简短回答。"
)

SURVEY_TARGET_TYPES = ("loyalfan", "casualviewer", "person")

REPORT_PLAN_SUPPLEMENT = """

【本场景为「创作者内容风险预演」】
模拟世界预演的是创作者发布一期内容后的受众反应。报告应回答：
1. 首波反应如何？铁粉与路人的评价分布怎样？
2. 争议点在哪里？哪些表达最容易引发批评与掉粉？
3. 品牌赞助方的敏感点是否被触发？平台审核风险有多大？
4. 争议是会自然消退还是持续发酵？创作者回应的最佳时机与方式是什么？
5. 给出替代表达建议：哪些段落重写可以规避风险且不损失内容价值。
建议章节方向：首波反应与粉丝态度分布、争议点与掉粉风险分析、
品牌方与平台风险评估、回应策略与替代表达建议。"""

REPORT_SECTION_SUPPLEMENT = """

【创作者内容风险章节写作要求】
- 引用观众关于"取关/不适/力挺"的原始发言作为风险证据
- 如工具结果中包含 market_metrics，必须引用具体数字（掉粉/争议词热度）
- 品牌方敏感点需引用品牌 Agent 的实际反应
- 替代表达建议必须具体到原句级改写，而非泛泛的风格建议"""

CAMPAIGN_OVERRIDES_DOC = "支持的变量：内容措辞（敏感表达替换）、发布时机、争议处理方式（回应/沉默/删改）。"

CREATOR_CONTENT_SCENARIO = Scenario(
    name="creator_content",
    label_key="home.scenarioLabelCreatorContent",
    description_key="home.scenarioDescCreatorContent",
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
        (("loyalfan", "person"), RULE_AGENT_FAN),
        (("casualviewer",), RULE_AGENT_VIEWER),
        (("critichater",), RULE_AGENT_CRITIC),
        (("brandsponsor", "company", "organization"), RULE_AGENT_SPONSOR),
        (("fellowcreator", "publicfigure"), RULE_AGENT_CREATOR),
        (("platformmoderator",), RULE_AGENT_MODERATOR),
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
