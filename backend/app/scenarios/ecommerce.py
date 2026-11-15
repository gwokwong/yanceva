"""电商新品上市预演场景。

把"新品上市"这一商业事件映射到 MiroFish 的社媒模拟世界：
- Agent：消费者、种草 KOL、行业专家、媒体、品牌官方、竞品品牌方
- 知识节点：Product（产品/单品）、Promotion（价格/促销活动）——只进图谱
  供检索与指标统计，不生成 Agent（节省模拟成本）
- 事件时间线：预热期 → 官宣 → 首销开售 → 长尾口碑（scheduled_events 注入
  首销/竞品反击等中途事件）
"""

from .base import Scenario

ONTOLOGY_SYSTEM_PROMPT = """你是一个专业的知识图谱本体设计专家。你的任务是分析给定的文本内容和模拟需求，设计适合**电商新品上市预演模拟**的实体类型和关系类型。

**重要：你必须输出有效的JSON格式数据，不要输出任何其他内容。**

## 核心任务背景

我们正在构建一个**电商新品上市预演模拟系统**。在这个系统中：
- 一部分实体是"发声主体"：消费者、种草KOL、行业专家、媒体、品牌官方、竞品品牌方——他们在社交媒体上讨论、种草、评测、回应
- 另一部分实体是"知识节点"：产品/单品、价格/促销活动——它们不是账号，不会发声，但会被讨论、被对比、被评价，是整个预演的核心对象

**两类实体都必须设计**：

**发声主体（可以在社媒上发声和互动）**：
- 消费者/潜在买家（普通用户、目标人群、老用户）
- 种草达人/KOL/博主（测评作者、直播带货、垂直领域达人）
- 行业专家/分析师
- 媒体机构（科技媒体、行业媒体、自媒体）
- 品牌官方账号（新品所属品牌）
- 竞品品牌方（竞品公司的官方账号）
- 平台/渠道（电商平台、线下渠道商）

**知识节点（不发声，但被讨论的对象）**：
- 产品/单品（本次新品、竞品产品）——属性通常包括价格、核心卖点、参数
- 促销/价格策略（首发价、优惠券、赠品、限时活动）

**不可以是**：
- 抽象概念（如"口碑"、"热度"、"购买欲"）
- 主题/话题（如"性价比"、"设计美学"）
- 观点/态度（如"支持方"、"反对方"）

## 输出格式

请输出JSON格式，包含以下结构：

```json
{
    "entity_types": [
        {
            "name": "实体类型名称（英文，PascalCase）",
            "description": "简短描述（英文，不超过100字符）",
            "attributes": [
                {
                    "name": "属性名（英文，snake_case）",
                    "type": "text",
                    "description": "属性描述"
                }
            ],
            "examples": ["示例实体1", "示例实体2"]
        }
    ],
    "edge_types": [
        {
            "name": "关系类型名称（英文，UPPER_SNAKE_CASE）",
            "description": "简短描述（英文，不超过100字符）",
            "source_targets": [
                {"source": "源实体类型", "target": "目标实体类型"}
            ],
            "attributes": []
        }
    ],
    "analysis_summary": "对文本内容的简要分析说明"
}
```

## 设计指南（极其重要！）

### 1. 实体类型设计 - 必须严格遵守

**数量要求：必须正好10个实体类型**

**层次结构要求（必须同时包含具体类型和兜底类型）**：

你的10个实体类型必须包含以下层次：

A. **兜底类型（必须包含，放在列表最后2个）**：
   - `Person`: 任何自然人个体的兜底类型。当一个人不属于其他更具体的人物类型时，归入此类。
   - `Organization`: 任何组织机构的兜底类型。当一个组织不属于其他更具体的组织类型时，归入此类。

B. **具体类型（8个，根据文本内容设计）**：
   - 必须覆盖三类角色：**发声主体**（消费者、KOL、品牌方等，至少4-5个）、**知识节点**（产品/价格类，至少1-2个）
   - 示例组合：`Consumer`, `KOLInfluencer`, `IndustryExpert`, `MediaOutlet`, `BrandOfficial`, `CompetitorBrand`, `Product`, `Promotion`
   - 产品知识节点的属性建议包含：`price`（价格）、`launch_date`（上市时间）、`key_feature`（核心卖点）、`is_competitor`（是否竞品）
   - 促销知识节点的属性建议包含：`discount`（折扣力度）、`channel`（渠道）、`promotion_period`（活动时间）

**为什么需要兜底类型**：
- 文本中会出现各种人物，如"路人甲"、"某位下单用户"
- 如果没有专门的类型匹配，他们应该被归入 `Person`
- 同理，小型经销商、临时团体等应该归入 `Organization`

**具体类型的设计原则**：
- 从文本中识别出高频出现或关键的角色类型
- 每个具体类型应该有明确的边界，避免重叠
- description 必须清晰说明这个类型和兜底类型的区别

### 2. 关系类型设计

- 数量：6-10个
- 关系应该反映电商语境下的真实联系，例如：
- INTERESTED_IN: 消费者对产品感兴趣
- RECOMMENDS: KOL推荐/种草产品
- REVIEWS: 评测/使用后评价
- MANUFACTURES: 品牌生产/发布产品
- COMPETES_WITH: 竞争关系（产品间、品牌间）
- PRICED_AT: 产品定价/参与促销
- REPORTS_ON: 报道
- PURCHASED: 购买了
- DISCUSSES: 讨论话题

### 3. 属性设计

- 每个实体类型1-3个关键属性
- **注意**：属性名不能使用 `name`、`uuid`、`group_id`、`graph_id`、`created_at`、`summary`（这些是系统保留字）
- 推荐使用：`price`, `launch_date`, `key_feature`, `follower_count`, `region`, `budget` 等

## 实体类型参考

**发声主体（具体）**：
- Consumer: 消费者/潜在买家
- KOLInfluencer: 种草达人/博主
- IndustryExpert: 行业专家/分析师
- MediaOutlet: 媒体机构
- BrandOfficial: 品牌官方账号
- CompetitorBrand: 竞品品牌方
- Merchant: 平台商家/店铺

**知识节点（具体）**：
- Product: 产品/单品（含竞品产品，用属性区分）
- Promotion: 价格/促销活动

**兜底类型**：
- Person: 任何自然人（不属于上述具体类型时使用）
- Organization: 任何组织机构（不属于上述具体类型时使用）

## 关系类型参考

- INTERESTED_IN: 感兴趣
- RECOMMENDS: 推荐/种草
- REVIEWS: 评测
- MANUFACTURES: 发布/生产
- COMPETES_WITH: 竞争
- PRICED_AT: 定价/促销
- PURCHASED: 购买
- REPORTS_ON: 报道
- DISCUSSES: 讨论
- RESPONDS_TO: 回应
"""

ONTOLOGY_USER_RULES = """
请根据以上内容，设计适合电商新品上市预演的实体类型和关系类型。

**必须遵守的规则**：
1. 必须正好输出10个实体类型
2. 最后2个必须是兜底类型：Person（个人兜底）和 Organization（组织兜底）
3. 前8个根据文本内容设计，必须同时覆盖发声主体（消费者/KOL/品牌方等）和知识节点（产品/价格促销类）
4. 产品、价格、促销等知识节点是合法实体（它们是被讨论的对象，不是账号）；但纯粹的抽象概念（口碑、热度、性价比）不可以
5. 属性名不能使用 name、uuid、group_id、graph_id 等保留字，用 product_title、price_point 等替代
"""

PERSONA_SYSTEM_PROMPT = "你是电商市场模拟专家，生成详细、真实的人物与账号设定用于新品上市预演模拟。必须返回有效的JSON格式，所有字符串值不能包含未转义的换行符。"

INDIVIDUAL_PERSONA_PROMPT = """为实体生成详细的社交媒体用户人设，用于电商新品上市预演模拟。

实体名称: {entity_name}
实体类型: {entity_type}
实体摘要: {entity_summary}
实体属性: {attrs_str}

上下文信息:
{context_str}

请生成JSON，包含以下字段:

1. bio: 社交媒体简介，200字
2. persona: 详细人设描述（2000字的纯文本），需包含:
   - 基本信息（年龄、职业、收入水平、所在城市、家庭状况）
   - 消费特征（月度消费预算、常用电商平台、决策风格：理性比价/冲动种草/品牌忠诚/极客尝鲜）
   - 品类关系（是否该品类老用户、正在用的产品、换机/回购周期）
   - 价格敏感度（对本次新品定价的接受区间、什么情况下会果断下单、什么情况下会放弃）
   - 社交媒体行为（活跃平台、发帖频率、内容偏好、互动风格、语言特点）
   - 对本品的初始态度（期待/观望/质疑/无感，以及形成该态度的原因）
   - 个人记忆（这个个体与本次新品事件的关联，以及已有的动作与反应）
3. age: 年龄数字（必须是整数）
4. gender: 性别，必须是英文: "male" 或 "female"
5. mbti: MBTI类型（如INTJ、ENFP等）
6. country: 国家（使用中文，如"中国"）
7. profession: 职业
8. interested_topics: 感兴趣话题数组

重要:
- 所有字段值必须是字符串或数字，不要使用换行符
- persona必须是一段连贯的文字描述
- {language_instruction} (gender字段必须用英文male/female)
- 内容要与实体信息保持一致
- age必须是有效的整数，gender必须是"male"或"female"
"""

GROUP_PERSONA_PROMPT = """为机构/品牌/群体实体生成详细的社交媒体账号设定，用于电商新品上市预演模拟。

实体名称: {entity_name}
实体类型: {entity_type}
实体摘要: {entity_summary}
实体属性: {attrs_str}

上下文信息:
{context_str}

请生成JSON，包含以下字段:

1. bio: 官方账号简介，200字，专业得体
2. persona: 详细账号设定描述（2000字的纯文本），需包含:
   - 机构基本信息（正式名称、机构性质、行业地位、主营业务）
   - 账号定位（账号类型、目标受众、核心功能；品牌官方侧重新品推广与用户沟通，竞品侧重防守与应对，媒体侧重评测报道）
   - 发言风格（语言特点、常用表达、禁忌话题）
   - 发布内容特点（内容类型、发布频率、活跃时间段；是否发布产品信息/促销信息/官方回应）
   - 立场态度（对本次新品事件的官方立场、面对争议的处理方式、与竞品的攻防关系）
   - 特殊说明（代表的群体画像、运营习惯、对价格与竞品动态的敏感点）
   - 机构记忆（这个机构与本次新品事件的关联，以及已有的动作与反应）
3. age: 固定填30（机构账号的虚拟年龄）
4. gender: 固定填"other"（机构账号使用other表示非个人）
5. mbti: MBTI类型，用于描述账号风格，如ISTJ代表严谨保守
6. country: 国家（使用中文，如"中国"）
7. profession: 机构职能描述
8. interested_topics: 关注领域数组

重要:
- 所有字段值必须是字符串或数字，不允许null值
- persona必须是一段连贯的文字描述，不要使用换行符
- {language_instruction} (gender字段必须用英文"other")
- age必须是整数30，gender必须是字符串"other"
- 机构账号发言要符合其身份定位"""

INDIVIDUAL_ENTITY_TYPES = (
    "consumer", "kolinfluencer", "industryexpert", "person",
    "publicfigure", "expert", "influencer", "livestreamer",
)

GROUP_ENTITY_TYPES = (
    "brandofficial", "competitorbrand", "mediaoutlet", "merchant",
    "organization", "company", "platform", "channel",
)

KNOWLEDGE_NODE_TYPES = ("product", "promotion", "productline", "category")

# max_agents 截断优先级：KOL/竞品/媒体/官方/专家优先保留，消费者抽样补足
AGENT_PRIORITY = (
    "competitorbrand", "kolinfluencer", "industryexpert", "mediaoutlet",
    "brandofficial", "merchant", "influencer", "livestreamer", "publicfigure",
    "expert", "consumer", "person", "organization", "company", "platform", "channel",
)

DEFAULT_MAX_AGENTS = 60

TIME_CONFIG_PROMPT = """基于以下新品上市预演需求，生成时间模拟配置。

{context_truncated}

## 任务
请生成时间配置JSON。时间线需要覆盖新品上市的完整节奏：预热期 → 官宣/发布会 → 首销开售 → 长尾口碑期。

### 电商场景作息参考（东八区，可按目标人群调整）：
- 凌晨0-6点几乎无人活动（活跃度系数0.05）
- 早上7-9点通勤刷手机渐活跃（活跃度系数0.4）
- 中午12-13点午休高峰（活跃度系数1.1）
- 工作时间9-12、14-18点中等活跃（活跃度系数0.6）
- 晚间19-23点是浏览、种草、下单的高峰（活跃度系数1.5）
- 首销开售当日（若有）应显著放大活跃度，开售前后各1-2小时为爆发时段
- 预热期讨论少、官宣日声量陡增、首销日达到峰值、长尾期回落

### 返回JSON格式（不要markdown）

示例：
{{
    "total_simulation_hours": 96,
    "minutes_per_round": 60,
    "agents_per_hour_min": 5,
    "agents_per_hour_max": 50,
    "peak_hours": [12, 13, 19, 20, 21, 22],
    "off_peak_hours": [0, 1, 2, 3, 4, 5],
    "morning_hours": [7, 8, 9],
    "work_hours": [9, 10, 11, 14, 15, 16, 17, 18],
    "reasoning": "针对该新品上市节奏的时间配置说明"
}}

字段说明：
- total_simulation_hours (int): 模拟总时长，48-168小时，覆盖预热到首销后的口碑期
- minutes_per_round (int): 每轮时长，30-120分钟，建议60分钟
- agents_per_hour_min (int): 每小时最少激活Agent数（取值范围: 1-{max_agents_allowed}）
- agents_per_hour_max (int): 每小时最多激活Agent数（取值范围: 1-{max_agents_allowed}）
- peak_hours (int数组): 高峰时段（午休+晚间购物高峰）
- off_peak_hours (int数组): 低谷时段，通常深夜凌晨
- morning_hours (int数组): 早间时段
- work_hours (int数组): 工作时段
- reasoning (string): 简要说明为什么这样配置"""

TIME_CONFIG_SYSTEM_PROMPT = "你是电商市场模拟专家。返回纯JSON格式，时间配置需符合新品上市节奏与目标消费群体的作息习惯。"

DEFAULT_TIME_CONFIG = {
    "total_simulation_hours": 96,
    "minutes_per_round": 60,
    "peak_hours": [12, 13, 19, 20, 21, 22],
    "off_peak_hours": [0, 1, 2, 3, 4, 5],
    "morning_hours": [7, 8, 9],
    "work_hours": [9, 10, 11, 14, 15, 16, 17, 18],
    "reasoning": "使用默认电商上市节奏配置（午休+晚间高峰）",
}

EVENT_CONFIG_PROMPT = """基于以下新品上市预演需求，生成事件配置。

模拟需求: {simulation_requirement}

{context_truncated}

## 可用实体类型及示例
{type_info}

## 任务
请生成事件配置JSON，预演"预热 → 官宣 → 首销 → 长尾"的上市时间线：

1. 提取热点话题关键词（产品名、价格争议点、竞品对比词、卖点词）
2. 描述市场舆论发展方向
3. 设计初始帖子内容（预热与官宣阶段），**每个帖子必须指定 poster_type（发布者类型）**：
   - 官宣帖：品牌官宣新品、定价与开售时间（BrandOfficial 类型发布）
   - 种草帖：KOL 上手体验、抢先评测（KOLInfluencer 类型发布）
   - 评测帖：媒体首发评测、参数解读（MediaOutlet 类型发布）
   - 期待/观望帖：普通消费者的讨论（Consumer 类型发布）
   - 竞品动态帖：竞品品牌的回应或预热（CompetitorBrand 类型发布）
4. 设计中途定时事件 scheduled_events（首销与后续阶段），每个事件必须指定 trigger_round（触发的轮次，从1开始计数，与模拟日志的 round 字段一致；0 保留给初始事件，不要使用）：
   - 首销开售：公布正式开售、价格与库存情况（trigger_round 建议在总轮次的40%-60%）
   - 竞品反击：竞品降价/发布对标卖点（trigger_round 建议在60%-80%）
   - 口碑事件：首批用户反馈发酵（好评或翻车）（trigger_round 建议60%之后）

**重要**: poster_type 必须从上面的"可用实体类型"中选择，这样初始帖子和定时事件才能分配给合适的 Agent 发布。

返回JSON格式（不要markdown）：
{{
    "hot_topics": ["关键词1", "关键词2", ...],
    "narrative_direction": "<市场舆论发展方向描述>",
    "initial_posts": [
        {{"content": "帖子内容", "poster_type": "实体类型（必须从可用类型中选择）"}},
        ...
    ],
    "scheduled_events": [
        {{"content": "事件帖内容", "poster_type": "实体类型", "trigger_round": 12, "event_name": "首销开售"}},
        ...
    ],
    "reasoning": "<简要说明>"
}}

注意：若无法从需求中确定总轮次，trigger_round 以 24 小时模拟、60 分钟/轮（共约 96 轮）为基准估算。"""

EVENT_CONFIG_SYSTEM_PROMPT = "你是电商市场分析专家。返回纯JSON格式。注意 poster_type 必须精确匹配可用实体类型，scheduled_events 的 trigger_round 必须是正整数。"

AGENT_CONFIG_PROMPT = """基于以下信息，为每个实体生成电商新品上市模拟的活动配置。

模拟需求: {simulation_requirement}

## 实体列表
```json
{entity_list_json}
```

## 任务
为每个实体生成活动配置，注意：
- **时间符合电商场景作息**：午休（12-13点）与晚间（19-23点）是消费讨论高峰
- **品牌官方**（BrandOfficial）：活跃度中低(0.3-0.5)，工作时间+官宣节点活跃，响应快(15-60分钟)，影响力高(2.5-3.0)，立场 supportive
- **种草KOL**（KOLInfluencer）：活跃度高(0.6-0.85)，午休+晚间活跃，响应快(10-60分钟)，影响力高(1.8-2.5)
- **行业专家**（IndustryExpert）：活跃度中(0.3-0.5)，影响力中高(1.5-2.0)
- **消费者**（Consumer）：活跃度中高(0.5-0.8)，午休+晚间活跃，响应快(1-15分钟)，影响力低(0.6-1.0)
- **竞品品牌**（CompetitorBrand）：活跃度低(0.2-0.4)，工作时间活动，影响力高(2.0-2.8)
- **媒体**（MediaOutlet）：全天活动(8-23)，影响力高(2.0-2.5)，立场 observer

返回JSON格式（不要markdown）：
{{
    "agent_configs": [
        {{
            "agent_id": <必须与输入一致>,
            "activity_level": <0.0-1.0>,
            "posts_per_hour": <发帖频率>,
            "comments_per_hour": <评论频率>,
            "active_hours": [<活跃小时列表，考虑电商场景作息>],
            "response_delay_min": <最小响应延迟分钟>,
            "response_delay_max": <最大响应延迟分钟>,
            "sentiment_bias": <-1.0到1.0>,
            "stance": "<supportive/opposing/neutral/observer>",
            "influence_weight": <影响力权重>
        }},
        ...
    ]
}}"""

AGENT_CONFIG_SYSTEM_PROMPT = "你是电商消费者行为分析专家。返回纯JSON，配置需符合新品上市场景中各角色的行为特征。"

RULE_AGENT_BRAND = {
    "activity_level": 0.4,
    "posts_per_hour": 0.3,
    "comments_per_hour": 0.2,
    "active_hours": list(range(9, 22)),  # 工作时间+晚间官宣节点
    "response_delay_min": 15,
    "response_delay_max": 60,
    "sentiment_bias": 0.0,
    "stance": "supportive",
    "influence_weight": 2.8,
}

RULE_AGENT_KOL = {
    "activity_level": 0.75,
    "posts_per_hour": 0.7,
    "comments_per_hour": 0.8,
    "active_hours": [12, 13, 19, 20, 21, 22, 23],  # 午休+晚间
    "response_delay_min": 10,
    "response_delay_max": 60,
    "sentiment_bias": 0.0,
    "stance": "neutral",
    "influence_weight": 2.0,
}

RULE_AGENT_CONSUMER = {
    "activity_level": 0.65,
    "posts_per_hour": 0.4,
    "comments_per_hour": 1.2,
    "active_hours": [7, 8, 12, 13, 19, 20, 21, 22, 23],  # 通勤+午休+晚间
    "response_delay_min": 1,
    "response_delay_max": 15,
    "sentiment_bias": 0.0,
    "stance": "neutral",
    "influence_weight": 0.8,
}

RULE_AGENT_COMPETITOR = {
    "activity_level": 0.3,
    "posts_per_hour": 0.2,
    "comments_per_hour": 0.1,
    "active_hours": list(range(9, 18)),  # 工作时间
    "response_delay_min": 30,
    "response_delay_max": 120,
    "sentiment_bias": 0.0,
    "stance": "opposing",
    "influence_weight": 2.4,
}

RULE_AGENT_MEDIA = {
    "activity_level": 0.5,
    "posts_per_hour": 0.8,
    "comments_per_hour": 0.3,
    "active_hours": list(range(8, 24)),  # 8:00-23:59
    "response_delay_min": 5,
    "response_delay_max": 30,
    "sentiment_bias": 0.0,
    "stance": "observer",
    "influence_weight": 2.2,
}

RULE_AGENT_EXPERT = {
    "activity_level": 0.4,
    "posts_per_hour": 0.3,
    "comments_per_hour": 0.5,
    "active_hours": list(range(9, 23)),
    "response_delay_min": 15,
    "response_delay_max": 90,
    "sentiment_bias": 0.0,
    "stance": "neutral",
    "influence_weight": 1.8,
}

RULE_AGENT_DEFAULT = {
    "activity_level": 0.6,
    "posts_per_hour": 0.4,
    "comments_per_hour": 1.0,
    "active_hours": [12, 13, 19, 20, 21, 22, 23],
    "response_delay_min": 2,
    "response_delay_max": 30,
    "sentiment_bias": 0.0,
    "stance": "neutral",
    "influence_weight": 1.0,
}

TYPE_ALIASES = {
    "brandofficial": ["brandofficial", "brand", "company", "organization"],
    "kol": ["kolinfluencer", "kol", "influencer", "blogger"],
    "consumer": ["consumer", "customer", "person", "user"],
    "competitorbrand": ["competitorbrand", "competitor", "rival", "company"],
    "mediaoutlet": ["mediaoutlet", "media"],
    "industryexpert": ["industryexpert", "expert", "professor", "analyst"],
    "merchant": ["merchant", "seller", "organization"],
    "product": ["product"],
}

# 静态指标关键词（产品名/竞品名在运行时从模拟配置动态补充）
METRIC_KEYWORDS = {
    "price": [
        "价格", "定价", "值不值", "贵", "便宜", "性价比", "多少钱", "降价", "涨价",
        "优惠", "折扣", "券", "预售", "比定价", "price", "expensive", "cheap", "discount",
    ],
    "purchase": [
        "买", "下单", "抢", "开售", "首销", "秒没", "库存", "缺货", "预售",
        "种草", "拔草", "入手", "buy", "purchase", "order", "sold out",
    ],
    "quality": [
        "质量", "做工", "续航", "性能", "体验", "评测", "翻车", "踩雷", "真香",
        "上手", "参数", "review", "quality", "performance", "battery",
    ],
    "competitor": [
        "竞品", "对比", "相比之下", "不如", "吊打", "对手", "同期", "vs", "比较",
        "competitor", "versus",
    ],
}

SURVEY_TEMPLATE = (
    "假设{product_name}已经上市开售："
    "1) 你会购买吗？请打1-5分（1=绝不买，5=一定买）；"
    "2) 你认为合理的价格是多少？"
    "3) 你最主要的顾虑是什么？请分三点用一两句话简短回答。"
)

SURVEY_TARGET_TYPES = ("consumer", "person", "customer")

REPORT_PLAN_SUPPLEMENT = """

【本场景为「电商新品上市预演」】
模拟世界预演的是一款新品上市后的市场反应。报告应回答：
1. 上市各阶段（预热/官宣/首销/长尾）的声量与情绪走势如何？
2. 消费者的购买意愿与价格接受度如何？价格是促成下单还是构成障碍？
3. KOL 种草与媒体报道带来了什么效果？哪些声音最有影响力？
4. 竞品的动态引发了哪些对比讨论？我们的卖点是否守住？
5. 有哪些上市风险（口碑翻车、价格争议、竞品截流）需要提前应对？
建议章节方向（可按模拟结果调整）：上市声量与情绪走势、购买意愿与价格接受度、
KOL与媒体效果评估、竞品对比与威胁分析、风险与行动建议。"""

REPORT_SECTION_SUPPLEMENT = """

【电商预演章节写作要求】
- 优先引用消费者关于"买不买、值不值、贵不贵"的原始发言作为购买意愿证据
- 如工具结果中包含 market_metrics（市场指标：声量、情绪、购买意愿、价格提及），
  必须引用具体数字支撑结论
- KOL 效果要看其内容引发的互动与转化讨论，而非只看粉丝量
- 竞品相关结论需引用真实的对比讨论内容"""

CAMPAIGN_OVERRIDES_DOC = (
    "支持的新品上市变量：定价（如 199→249）、首发促销力度、KOL 投放组合、"
    "上市时间节奏（提前/延后首销）。"
)

ECOMMERCE_SCENARIO = Scenario(
    name="ecommerce",
    label_key="home.scenarioLabelEcommerce",
    description_key="home.scenarioDescEcommerce",
    ontology_system_prompt=ONTOLOGY_SYSTEM_PROMPT,
    ontology_user_rules=ONTOLOGY_USER_RULES,
    persona_system_prompt=PERSONA_SYSTEM_PROMPT,
    individual_persona_prompt=INDIVIDUAL_PERSONA_PROMPT,
    group_persona_prompt=GROUP_PERSONA_PROMPT,
    individual_entity_types=INDIVIDUAL_ENTITY_TYPES,
    group_entity_types=GROUP_ENTITY_TYPES,
    knowledge_node_types=KNOWLEDGE_NODE_TYPES,
    agent_priority=AGENT_PRIORITY,
    default_max_agents=DEFAULT_MAX_AGENTS,
    time_config_prompt=TIME_CONFIG_PROMPT,
    time_config_system_prompt=TIME_CONFIG_SYSTEM_PROMPT,
    default_time_config=DEFAULT_TIME_CONFIG,
    event_config_prompt=EVENT_CONFIG_PROMPT,
    event_config_system_prompt=EVENT_CONFIG_SYSTEM_PROMPT,
    agent_config_prompt=AGENT_CONFIG_PROMPT,
    agent_config_system_prompt=AGENT_CONFIG_SYSTEM_PROMPT,
    rule_agent_configs=(
        (("brandofficial", "company"), RULE_AGENT_BRAND),
        (("kolinfluencer", "influencer", "livestreamer"), RULE_AGENT_KOL),
        (("consumer", "customer"), RULE_AGENT_CONSUMER),
        (("competitorbrand",), RULE_AGENT_COMPETITOR),
        (("mediaoutlet",), RULE_AGENT_MEDIA),
        (("industryexpert", "expert", "publicfigure"), RULE_AGENT_EXPERT),
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
