"""品牌危机回应预演场景。

预演品牌危机事件（质量事故/舆论风波/服务事故）的传播与发酵：
传播路径、用户愤怒演化、媒体追责、回应话术与时点的效果、二次引爆点。
"""

from .base import Scenario

ONTOLOGY_SYSTEM_PROMPT = """你是一个专业的知识图谱本体设计专家。你的任务是分析给定的文本内容和模拟需求，设计适合**品牌危机回应预演模拟**的实体类型和关系类型。

**重要：你必须输出有效的JSON格式数据，不要输出任何其他内容。**

## 核心任务背景

我们正在构建一个**品牌危机回应预演沙盘**。场景：品牌发生危机事件（产品事故/服务风波/不当言论等），预演事件的传播路径与各方的反应，并测试不同的回应话术与时点。其中：
- 一部分实体是"发声主体"：受影响用户（当事人）、吃瓜群众、调查记者、危机公关KOL、品牌官方、监管部门、竞品
- 另一部分实体是"知识节点"：危机事件本身、回应声明——它们是被讨论和传播的对象

**不可以是**：抽象概念（"舆情"、"愤怒值"）、主题（"公关策略"）、观点（"支持方"）。

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
   - 发声主体示例：`AffectedUser`（受影响用户/当事人）、`Bystander`（吃瓜群众）、`InvestigativeJournalist`（调查记者）、`CrisisKOL`（危机公关/舆论意见领袖）、`BrandOfficial`（品牌官方）、`Regulator`（监管部门）
   - 知识节点示例：`CrisisIncident`（危机事件，属性含 severity/date）、`Statement`（回应声明）

### 2. 关系类型设计（6-10个）
`AFFECTED_BY`（受影响）、`SPREADS`（传播）、`INVESTIGATES`（调查）、`ISSUES_STATEMENT`（发布声明）、`DEMANDS_REFUND`（索赔）、`AMPLIFIES`（放大）、`CRITICIZES`、`REGULATES`。

### 3. 属性设计
1-3个属性；禁用 `name/uuid/group_id/graph_id/created_at/summary`。
"""

ONTOLOGY_USER_RULES = """
请根据以上内容，设计适合品牌危机回应预演的实体类型和关系类型。

**必须遵守的规则**：
1. 正好10个实体类型；最后2个是 Person/Organization 兜底
2. 前8个必须同时覆盖发声主体（受影响用户/吃瓜群众/记者/KOL/品牌官方/监管）和知识节点（危机事件/回应声明）
3. 抽象概念不可以；危机事件与回应声明是合法知识节点
4. 属性名禁用系统保留字
"""

PERSONA_SYSTEM_PROMPT = "你是危机公关与舆情模拟专家，生成详细、真实的人物与账号设定用于品牌危机回应预演。必须返回有效的JSON格式，所有字符串值不能包含未转义的换行符。"

INDIVIDUAL_PERSONA_PROMPT = """为实体生成详细的社交媒体用户人设，用于品牌危机回应预演。

实体名称: {entity_name}
实体类型: {entity_type}
实体摘要: {entity_summary}
实体属性: {attrs_str}

上下文信息:
{context_str}

请生成JSON，包含以下字段:

1. bio: 社交媒体简介，200字
2. persona: 详细人设描述（2000字的纯文本），需包含:
   - 基本信息（年龄、职业、与危机事件的关系：直接受影响/目击/关注）
   - 受影响程度（损失了什么、诉求是什么：退款/道歉/赔偿/追责）
   - 传播行为（转发习惯、情绪表达方式、什么会触发TA扩散或平静下来）
   - 对品牌回应的敏感点（官方话术中的什么会让TA更愤怒——甩锅/拖延/格式化道歉；什么会让TA缓和——真诚/具体措施/负责人出面）
   - 社交媒体行为（活跃时段、发帖频率、语言特点）
   - 个人记忆（与本次危机事件的关联及已有反应）
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

GROUP_PERSONA_PROMPT = """为品牌/机构实体生成详细的账号设定，用于品牌危机回应预演。

实体名称: {entity_name}
实体类型: {entity_type}
实体摘要: {entity_summary}
实体属性: {attrs_str}

上下文信息:
{context_str}

请生成JSON，包含以下字段:

1. bio: 官方账号简介，200字
2. persona: 详细账号设定描述（2000字的纯文本），需包含:
   - 机构基本信息（品牌/媒体/监管机构的名称、性质）
   - 账号定位（品牌官方：危机沟通职能与姿态；调查记者：追责与深度报道；监管机构：依法依规处置）
   - 发言风格（品牌官方的危机话术风格；记者的报道风格）
   - 发布内容特点（危机期间的发布频率、内容类型）
   - 立场态度（对危机事件的立场、与当事用户的沟通方式）
   - 机构记忆（与本次危机事件的关联及已有动作）
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
    "affecteduser", "bystander", "investigativejournalist", "crisiskol", "person",
)

GROUP_ENTITY_TYPES = (
    "brandofficial", "regulator", "mediaoutlet", "organization", "company",
)

KNOWLEDGE_NODE_TYPES = ("crisisincident", "statement", "incident", "statementletter")

AGENT_PRIORITY = (
    "affecteduser", "investigativejournalist", "crisiskol", "brandofficial",
    "regulator", "mediaoutlet", "publicfigure", "bystander", "person",
    "organization", "company",
)

DEFAULT_MAX_AGENTS = 60

TIME_CONFIG_PROMPT = """基于以下品牌危机回应预演需求，生成时间模拟配置。

{context_truncated}

## 任务
请生成时间配置JSON。危机传播的特点是**全天候病毒式发酵**：黄金4小时 → 24小时定调 → 48-72小时二次引爆或平息。

### 危机传播作息参考（东八区，可按事件调整）：
- 危机传播没有作息——全天维持基础活跃度，事件爆发后深夜也有讨论
- 早8-10点媒体早报跟进（系数1.2）
- 午12-13点碎片化传播高峰（系数1.3）
- 晚19-24点黄金发酵期（系数1.6）
- 回应发布后的1-2小时是关键窗口（舆论转向或恶化）

### 返回JSON格式（不要markdown）

示例：
{{
    "total_simulation_hours": 72,
    "minutes_per_round": 60,
    "agents_per_hour_min": 8,
    "agents_per_hour_max": 60,
    "peak_hours": [12, 13, 19, 20, 21, 22, 23],
    "off_peak_hours": [3, 4],
    "morning_hours": [8, 9],
    "work_hours": [10, 11, 14, 15, 16, 17, 18],
    "reasoning": "针对该危机传播节奏的时间配置说明"
}}

字段说明：
- total_simulation_hours (int): 48-96小时（危机以72小时为黄金窗口）
- minutes_per_round (int): 建议60分钟
- agents_per_hour_min/max (int): 取值范围 1-{max_agents_allowed}（危机期建议偏高）
- peak_hours / off_peak_hours / morning_hours / work_hours (int数组)
- reasoning (string)"""

TIME_CONFIG_SYSTEM_PROMPT = "你是危机公关与舆情模拟专家。返回纯JSON格式，危机传播是全天候的，活跃度不应有过低的时段。"

DEFAULT_TIME_CONFIG = {
    "total_simulation_hours": 72,
    "minutes_per_round": 60,
    "peak_hours": [12, 13, 19, 20, 21, 22, 23],
    "off_peak_hours": [3, 4],
    "morning_hours": [8, 9],
    "work_hours": [10, 11, 14, 15, 16, 17, 18],
    "reasoning": "使用默认危机传播节奏配置（全天候高活跃）",
}

EVENT_CONFIG_PROMPT = """基于以下品牌危机回应预演需求，生成事件配置。

模拟需求: {simulation_requirement}

{context_truncated}

## 可用实体类型及示例
{type_info}

## 任务
请生成事件配置JSON，预演"事件爆发 → 舆论发酵 → 官方回应 → 二次发酵/平息"的完整危机时间线：

1. 提取热点话题关键词（事件名、品牌名、索赔词、抵制词）
2. 描述舆情传播方向（从哪个群体向哪个群体扩散、会引爆什么次生话题）
3. 设计初始帖子（危机爆发与首波反应），**每个帖子必须指定 poster_type**：
   - 当事人爆料/维权帖（AffectedUser 类型）
   - 吃瓜群众扩散（Bystander 类型）
   - 媒体跟进报道（MediaOutlet 类型）
   - KOL 锐评（CrisisKOL 类型）
4. 设计中途定时事件 scheduled_events（这是本场景的核心：**测试不同的回应话术与时点**），每个事件必须指定 trigger_round（从1开始计数，0 保留）：
   - 品牌第一次回应：黄金4小时内回应/拖延24小时后回应（trigger_round 决定时点，内容决定话术）
   - 媒体深度调查报道（trigger_round 建议30%-50%）
   - 监管介入/集体索赔升级（trigger_round 建议50%-70%）
   - 二次引爆点：回应被批"格式化道歉"/补救措施被认可（trigger_round 建议60%-80%）

**重要**: poster_type 必须从"可用实体类型"中选择。回应声明的措辞请按需求中给出的品牌话术生成。

返回JSON格式（不要markdown）：
{{
    "hot_topics": ["关键词1", ...],
    "narrative_direction": "<舆情传播方向>",
    "initial_posts": [
        {{"content": "帖子内容", "poster_type": "实体类型"}},
        ...
    ],
    "scheduled_events": [
        {{"content": "事件帖/回应声明内容", "poster_type": "实体类型", "trigger_round": 4, "event_name": "品牌第一次回应"}},
        ...
    ],
    "reasoning": "<简要说明>"
}}"""

EVENT_CONFIG_SYSTEM_PROMPT = "你是危机公关分析师。返回纯JSON格式。poster_type 必须精确匹配可用实体类型，scheduled_events 的 trigger_round 必须是正整数且从1开始。回应声明帖的措辞必须体现品牌指定的回应话术。"

AGENT_CONFIG_PROMPT = """基于以下信息，为每个实体生成品牌危机回应模拟的活动配置。

模拟需求: {simulation_requirement}

## 实体列表
```json
{entity_list_json}
```

## 任务
为每个实体生成活动配置，注意：
- **危机传播是全天候的**，各角色活跃度整体调高
- **受影响用户**（AffectedUser）：活跃度极高(0.8-0.95)，全天活跃，响应极快(1-10分钟)，sentiment_bias 偏负(-0.3~-0.6)，影响力取决于粉丝量
- **吃瓜群众**（Bystander）：活跃度高(0.6-0.8)，围观扩散，影响力低(0.5-0.9)
- **调查记者**（InvestigativeJournalist）：活跃度高(0.6-0.8)，深度报道，影响力高(2.0-2.8)
- **危机公关KOL**（CrisisKOL）：活跃度高(0.6-0.8)，专业点评回应话术，影响力高(1.8-2.5)
- **品牌官方**（BrandOfficial）：活跃度中(0.4-0.6)，回应节点爆发，影响力高(2.5-3.5)，supportive
- **监管机构**（Regulator）：活跃度低(0.1-0.3)，关键时刻介入，影响力极高(3.5)
- **媒体**（MediaOutlet）：全天，影响力高(2.0-2.5)

返回JSON格式（不要markdown）：
{{
    "agent_configs": [
        {{
            "agent_id": <必须与输入一致>,
            "activity_level": <0.0-1.0>,
            "posts_per_hour": <发帖频率>,
            "comments_per_hour": <评论频率>,
            "active_hours": [<活跃小时列表，危机期间应覆盖全天>],
            "response_delay_min": <最小响应延迟分钟>,
            "response_delay_max": <最大响应延迟分钟>,
            "sentiment_bias": <-1.0到1.0，受影响用户应为负值>,
            "stance": "<supportive/opposing/neutral/observer>",
            "influence_weight": <影响力权重>
        }},
        ...
    ]
}}"""

AGENT_CONFIG_SYSTEM_PROMPT = "你是危机公关分析师。返回纯JSON，危机传播期间各角色活跃度应整体高于日常。"

RULE_AGENT_AFFECTED = {
    "activity_level": 0.9, "posts_per_hour": 0.8, "comments_per_hour": 2.0,
    "active_hours": list(range(0, 24)), "response_delay_min": 1, "response_delay_max": 10,
    "sentiment_bias": -0.5, "stance": "opposing", "influence_weight": 1.5,
}
RULE_AGENT_BYSTANDER = {
    "activity_level": 0.7, "posts_per_hour": 0.5, "comments_per_hour": 1.5,
    "active_hours": [12, 13, 19, 20, 21, 22, 23], "response_delay_min": 2,
    "response_delay_max": 20, "sentiment_bias": -0.2, "stance": "neutral", "influence_weight": 0.7,
}
RULE_AGENT_JOURNALIST = {
    "activity_level": 0.7, "posts_per_hour": 0.7, "comments_per_hour": 0.4,
    "active_hours": list(range(8, 24)), "response_delay_min": 5, "response_delay_max": 40,
    "sentiment_bias": 0.0, "stance": "observer", "influence_weight": 2.5,
}
RULE_AGENT_BRAND = {
    "activity_level": 0.5, "posts_per_hour": 0.3, "comments_per_hour": 0.3,
    "active_hours": list(range(8, 24)), "response_delay_min": 10, "response_delay_max": 45,
    "sentiment_bias": 0.0, "stance": "supportive", "influence_weight": 3.0,
}
RULE_AGENT_REGULATOR = {
    "activity_level": 0.2, "posts_per_hour": 0.1, "comments_per_hour": 0.05,
    "active_hours": list(range(9, 18)), "response_delay_min": 120, "response_delay_max": 480,
    "sentiment_bias": 0.0, "stance": "observer", "influence_weight": 3.5,
}
RULE_AGENT_KOL = {
    "activity_level": 0.7, "posts_per_hour": 0.6, "comments_per_hour": 0.7,
    "active_hours": list(range(8, 24)), "response_delay_min": 5, "response_delay_max": 40,
    "sentiment_bias": 0.0, "stance": "neutral", "influence_weight": 2.0,
}
RULE_AGENT_DEFAULT = {
    "activity_level": 0.7, "posts_per_hour": 0.5, "comments_per_hour": 1.5,
    "active_hours": list(range(8, 24)), "response_delay_min": 2,
    "response_delay_max": 20, "sentiment_bias": -0.1, "stance": "neutral", "influence_weight": 1.0,
}

TYPE_ALIASES = {
    "affecteduser": ["affecteduser", "victim", "person"],
    "bystander": ["bystander", "person", "netizen"],
    "investigativejournalist": ["investigativejournalist", "journalist", "media", "reporter"],
    "crisiskol": ["crisiskol", "kol", "pr", "person"],
    "brandofficial": ["brandofficial", "brand", "company", "organization"],
    "regulator": ["regulator", "government", "organization"],
    "mediaoutlet": ["mediaoutlet", "media"],
    "crisisincident": ["crisisincident"],
    "statement": ["statement"],
}

METRIC_KEYWORDS = {
    "outrage": ["愤怒", "恶心", "无耻", "抵制", "黑心", "退款", "索赔", "投诉", "angry", "boycott", "refund"],
    "spread": ["扩散", "转发", "上热搜", "全网", "发酵", "二次传播", "viral", "trending"],
    "response": ["回应", "声明", "道歉", "甩锅", "拖延", "格式化道歉", "statement", "apology"],
    "escalation": ["监管", "介入", "起诉", "集体", "维权", "升级", "regulator", "lawsuit", "escalate"],
}

SURVEY_TEMPLATE = (
    "品牌已就《{product_name}》事件发布回应：1) 这个回应你能接受吗（1-5分，5=完全接受）？"
    "2) 回应里最让你不满或最让你认可的一点是什么？3) 你接下来会怎么做（继续维权/观察/放弃）？请简短回答。"
)

SURVEY_TARGET_TYPES = ("affecteduser", "bystander", "person")

REPORT_PLAN_SUPPLEMENT = """

【本场景为「品牌危机回应预演」】
模拟世界预演的是品牌危机事件的传播与回应效果。报告应回答：
1. 传播路径：危机从哪个群体爆发、经谁放大、扩散到哪些圈层？关键传播节点是谁？
2. 情绪演化：愤怒值如何随时间变化？回应发布后是转向还是恶化？
3. 回应话术效果：哪句话引发二次引爆、哪句话获得认可？回应时点的影响？
4. 次生风险：监管介入/集体索赔/媒体深挖的可能性有多大？
5. 给出回应策略的明确结论：最佳回应时点、话术要点、必须避免的雷区。
建议章节方向：危机传播路径复盘、情绪与舆论演化时间线、回应效果评估、
次生风险预警、回应策略与话术建议。"""

REPORT_SECTION_SUPPLEMENT = """

【危机预演章节写作要求】
- 引用受影响用户的原始维权发言与吃瓜群众的扩散发言作为传播证据
- 如工具结果中包含 market_metrics，必须引用愤怒值/扩散词/回应词的具体数字
- 回应效果评估必须对比回应发布前后的情绪变化
- 必须明确指出二次引爆点（如有）及其触发条件"""

CAMPAIGN_OVERRIDES_DOC = "支持的变量：回应话术（道歉/补偿/甩锅对比）、回应时点（黄金4小时/拖延24小时）、补偿方案力度。"

BRAND_CRISIS_SCENARIO = Scenario(
    name="brand_crisis",
    label_key="home.scenarioLabelBrandCrisis",
    description_key="home.scenarioDescBrandCrisis",
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
        (("affecteduser", "person"), RULE_AGENT_AFFECTED),
        (("bystander",), RULE_AGENT_BYSTANDER),
        (("investigativejournalist", "mediaoutlet"), RULE_AGENT_JOURNALIST),
        (("brandofficial", "company", "organization"), RULE_AGENT_BRAND),
        (("regulator",), RULE_AGENT_REGULATOR),
        (("crisiskol", "publicfigure"), RULE_AGENT_KOL),
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
