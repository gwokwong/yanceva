"""商品目录（SKU）模型与管理。

平台上的每个"服务"（如 电商新品上市预演）是一条 SKU 记录：
场景包 + 提交表单 schema + 报告模板 + 定价 + 成本预算（max_agents/
轮数/变体数）——上线新服务 = 新增一条 SKU + 一个 Scenario 包，
平台代码零改动。

目录持久化为 JSON 文件（uploads/products/catalog.json），首次访问时
播种内置 SKU。修改目录直接编辑该文件（管理操作暂不做 UI）。
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger('mirofish.product')

# 订单形态
KIND_SIMULATION = "simulation"   # 完整多智能体沙盘
KIND_REVIEW = "review"           # 轻量多角色评审团（无模拟）


@dataclass
class Product:
    """一条可购买的服务（SKU）"""
    product_id: str
    name: str
    kind: str = KIND_SIMULATION
    scenario: str = "ecommerce"
    tagline: str = ""
    # 定价（美分，避免浮点）
    price_cents: int = 4900
    currency: str = "USD"
    # 交付承诺
    sla_minutes: int = 120
    deliverable_name: str = "预演报告"
    # 提交表单（JSON Schema 子集：properties/required，前端动态渲染）
    intake_schema: Dict[str, Any] = field(default_factory=dict)
    # 成本预算 → 毛利护栏
    budget: Dict[str, Any] = field(default_factory=lambda: {
        "max_agents": 40,
        "max_rounds": 48,
        "variants": 0,
    })
    # 展示与路由
    priority: int = 0            # 队列优先级（越大越先）
    hidden: bool = False         # 内部/开发 SKU 不对外展示
    active: bool = True
    # 报告增量（注入场景包报告 prompt 之后的 SKU 级补充）
    report_supplement: str = ""
    # Creem 商品的 prod_xxx（在 creem.io 后台创建对应产品后填入；用于 Checkout）
    creem_product_id: Optional[str] = None
    # 多语言覆盖：{"en": {"name": ..., "tagline": ..., "deliverable_name": ..., "intake_schema": {...}}}
    # 基础字段（name/tagline/intake_schema）为默认语言（zh）；API 按 Accept-Language 合并
    i18n: Dict[str, Any] = field(default_factory=dict)
    # 即将上线（占位展示，不可下单）
    coming_soon: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Product':
        return cls(
            product_id=data['product_id'],
            name=data.get('name', ''),
            kind=data.get('kind', KIND_SIMULATION),
            scenario=data.get('scenario', 'ecommerce'),
            tagline=data.get('tagline', ''),
            price_cents=int(data.get('price_cents', 4900)),
            currency=data.get('currency', 'USD'),
            sla_minutes=int(data.get('sla_minutes', 120)),
            deliverable_name=data.get('deliverable_name', '预演报告'),
            intake_schema=data.get('intake_schema', {}),
            budget=data.get('budget', {}),
            priority=int(data.get('priority', 0)),
            hidden=bool(data.get('hidden', False)),
            active=bool(data.get('active', True)),
            report_supplement=data.get('report_supplement', ''),
            creem_product_id=data.get('creem_product_id'),
            coming_soon=bool(data.get('coming_soon', False)),
            i18n=data.get('i18n', {}),
        )

    def localized(self, language: str) -> Dict[str, Any]:
        """返回按语言合并后的展示字段（en 命中 i18n 覆盖则替换，否则回退默认中文）。"""

        data = {
            "name": self.name,
            "tagline": self.tagline,
            "deliverable_name": self.deliverable_name,
            "intake_schema": self.intake_schema,
        }
        override = (self.i18n or {}).get((language or "zh").lower().split("-")[0])
        if isinstance(override, dict):
            for key, value in override.items():
                if value:
                    data[key] = value
        return data

    def to_public_dict(self, language: str = "zh") -> Dict[str, Any]:
        """对外暴露的字段（按语言本地化；不含内部预算细节）。"""

        localized = self.localized(language)
        out = {
            "product_id": self.product_id,
            "kind": self.kind,
            "scenario": self.scenario,
            "price_cents": self.price_cents,
            "currency": self.currency,
            "sla_minutes": self.sla_minutes,
            "coming_soon": self.coming_soon,
            "orderable": not (self.hidden or self.coming_soon) and self.active,
        }
        out.update(localized)
        return out

# ── 内置 SKU 播种 ──────────────────────────────────────────────

_ECOMMERCE_INTAKE = {
    "type": "object",
    "required": ["product_name", "price_point", "target_audience", "launch_plan"],
    "properties": {
        "product_name": {"type": "string", "title": "产品名称", "placeholder": "星尘降噪耳机X"},
        "price_point": {"type": "string", "title": "定价", "placeholder": "599元 / $79.99"},
        "target_audience": {"type": "text", "title": "目标人群", "placeholder": "25-35岁一二线城市通勤白领，月消费预算2000-5000元"},
        "key_features": {"type": "text", "title": "核心卖点", "placeholder": "42dB主动降噪、60小时续航、首发赠耳机包", "required": False},
        "competitors": {"type": "text", "title": "主要竞品", "placeholder": "悦耳AirPro（499元，市场份额领先）", "required": False},
        "launch_plan": {"type": "text", "title": "上市计划", "placeholder": "官宣后第3天预售，第7天首销；投放10位数码KOL，2家科技媒体首发评测"},
        "concerns": {"type": "text", "title": "你最担心的风险（可选）", "required": False},
    },
}


_ECOMMERCE_INTAKE_EN = {
    "type": "object",
    "required": ["product_name", "price_point", "target_audience", "launch_plan"],
    "properties": {
        "product_name": {"type": "string", "title": "Product name", "placeholder": "StarDust Noise-Cancelling Earbuds X"},
        "price_point": {"type": "string", "title": "Price point", "placeholder": "$79.99"},
        "target_audience": {"type": "text", "title": "Target audience", "placeholder": "Commuters aged 25-35, monthly budget $300-700"},
        "key_features": {"type": "text", "title": "Key features", "placeholder": "42dB ANC, 60-hour battery, launch bundle", "required": False},
        "competitors": {"type": "text", "title": "Main competitors", "placeholder": "AirPro ($69, market leader)", "required": False},
        "launch_plan": {"type": "text", "title": "Launch plan", "placeholder": "Pre-order day 3, on-sale day 7; 10 tech KOLs seeded, 2 media reviews"},
        "concerns": {"type": "text", "title": "Biggest worry (optional)", "required": False},
    },
}

_LISTING_INTAKE_EN = {
    "type": "object",
    "required": ["listing_title", "listing_description", "target_markets"],
    "properties": {
        "listing_title": {"type": "string", "title": "Listing title", "placeholder": "StarDust ANC Headphones - 60H Battery, CE Certified"},
        "listing_description": {"type": "text", "title": "Listing description (with bullets)", "placeholder": "• 42dB active noise cancellation\n• 60-hour battery\n• Premium gift-ready packaging"},
        "target_markets": {"type": "string", "title": "Target markets (comma-separated)", "placeholder": "US, Germany, UAE, Japan"},
        "platform": {"type": "string", "title": "Sales channel", "placeholder": "Amazon US / Etsy / Shopify store", "required": False},
        "product_name": {"type": "string", "title": "Product name", "required": False},
    },
}

_SAAS_INTAKE_EN = {
    "type": "object",
    "required": ["product_name", "pricing_change", "target_users"],
    "properties": {
        "product_name": {"type": "string", "title": "Product name", "placeholder": "NoteForge collaborative notes ($12/mo Pro)"},
        "pricing_change": {"type": "text", "title": "Pricing / redesign plan", "placeholder": "Pro $12 → $15/mo; free tier collab cap 5 → 2; new AI features"},
        "target_users": {"type": "string", "title": "Target users", "placeholder": "Indie devs & small teams (5-20), 3,000 paying users"},
        "competitors": {"type": "string", "title": "Competitors & alternatives", "placeholder": "Notion ($10/mo), Obsidian (free)", "required": False},
        "concerns": {"type": "text", "title": "Biggest worry (optional)", "required": False},
    },
}

_CRISIS_INTAKE_EN = {
    "type": "object",
    "required": ["brand_name", "incident_description"],
    "properties": {
        "brand_name": {"type": "string", "title": "Brand name", "placeholder": "StarDust Tech"},
        "incident_description": {"type": "text", "title": "Incident description", "placeholder": "Charging case overheated and lightly burned a user's hand; user posted photos demanding a recall; Weibo discussion rising fast"},
        "planned_response": {"type": "text", "title": "Draft response script (multiple versions for A/B)", "placeholder": "Version A: apology within 4h + full refund + free replacement\nVersion B: publish investigation after 24h + recall", "required": False},
        "audience": {"type": "string", "title": "Audience & spread channels", "placeholder": "tech circles → Weibo trending → business media", "required": False},
        "concerns": {"type": "text", "title": "Biggest worry (optional)", "required": False},
    },
}

_COMPETITOR_INTAKE_EN = {
    "type": "object",
    "required": ["product_name", "competitor_announcement", "target_audience"],
    "properties": {
        "product_name": {"type": "string", "title": "Our product", "placeholder": "StarDust Earbuds X ($79.99)"},
        "competitor_announcement": {"type": "text", "title": "Competitor launch move", "placeholder": "AirPro announces AirPro 2 at $69 with spatial audio, on sale next week"},
        "our_strengths": {"type": "text", "title": "Our strengths & response resources", "placeholder": "Better ANC, loyal user base; can discount $25 / publish comparison / push firmware update", "required": False},
        "target_audience": {"type": "string", "title": "Target users", "placeholder": "Commuters aged 25-35"},
        "concerns": {"type": "text", "title": "Biggest worry (optional)", "required": False},
    },
}

_CREATOR_INTAKE_EN = {
    "type": "object",
    "required": ["product_name", "content_topic", "content_outline"],
    "properties": {
        "product_name": {"type": "string", "title": "Creator / channel", "placeholder": "@TechDaily (500K subscribers)"},
        "content_topic": {"type": "string", "title": "Episode topic", "placeholder": "'Why I'm ditching iPhone for a folding phone'"},
        "content_outline": {"type": "text", "title": "Outline / key statements", "placeholder": "Opening rant about iPhone heat → head-to-head vs folding phones → admits sponsor deal → claim: Apple innovation is dead"},
        "audience": {"type": "string", "title": "Audience", "placeholder": "18-35 tech enthusiasts, mixed iOS/Android", "required": False},
        "concerns": {"type": "text", "title": "Biggest worry (optional)", "required": False},
    },
}


def _seed_products() -> List[Product]:
    return [
        Product(
            product_id="ecommerce_launch_std",
            name="电商新品上市预演 · 标准版",
            kind=KIND_SIMULATION,
            scenario="ecommerce",
            tagline="40 个消费者/KOL/竞品/媒体 Agent，48 小时市场推演，交付买家反应、差评风险、竞品反应与转化阻力报告",
            price_cents=2900,
            sla_minutes=120,
            deliverable_name="买家反应与转化阻力报告",
            intake_schema=_ECOMMERCE_INTAKE,
            budget={"max_agents": 40, "max_rounds": 48, "variants": 0},
            priority=10,
            i18n={"en": {
                "name": "E-commerce Launch Rehearsal · Standard",
                "tagline": "40 simulated buyers/KOLs/competitors/media agents, a 48-hour market rollout. Delivers buyer reaction, review risks, competitor response and conversion-friction report.",
                "deliverable_name": "Buyer Reaction & Conversion Friction Report",
                "intake_schema": {
                    "type": "object",
                    "required": ["product_name", "price_point", "target_audience", "launch_plan"],
                    "properties": {
                        "product_name": {"type": "string", "title": "Product name", "placeholder": "StarDust Noise-Cancelling Earbuds X"},
                        "price_point": {"type": "string", "title": "Price point", "placeholder": "$79.99"},
                        "target_audience": {"type": "text", "title": "Target audience", "placeholder": "Commuters aged 25-35 in tier-1 cities, monthly discretionary budget $300-700"},
                        "key_features": {"type": "text", "title": "Key features", "placeholder": "42dB ANC, 60-hour battery, launch bundle", "required": False},
                        "competitors": {"type": "text", "title": "Main competitors", "placeholder": "AirPro (cheaper, market leader)", "required": False},
                        "launch_plan": {"type": "text", "title": "Launch plan", "placeholder": "Pre-order day 3, on-sale day 7; 10 tech KOLs seeded, 2 media reviews"},
                        "concerns": {"type": "text", "title": "Biggest worry (optional)", "required": False},
                    },
                },
            }},
            report_supplement=(
                "\n【本报告为商业交付物，买家需按交付标准阅读】\n"
                "- 最后一章必须是「行动建议」：给出 3-5 条可在上市前执行的具体动作\n"
                "- 差评风险需按严重程度排序，并指出触发人群与触发条件\n"
            ),
        ),
        Product(
            product_id="ecommerce_launch_pro",
            name="电商新品上市预演 · 专业版",
            kind=KIND_SIMULATION,
            scenario="ecommerce",
            tagline="60 个 Agent × 96 小时深度推演 + 2 个变量变体（如定价 A/B），附对比结论",
            price_cents=5900,
            sla_minutes=240,
            deliverable_name="买家反应与转化阻力报告（含 A/B 对比）",
            intake_schema=_ECOMMERCE_INTAKE,
            budget={"max_agents": 60, "max_rounds": 96, "variants": 2},
            priority=20,
            i18n={"en": {
                "name": "E-commerce Launch Rehearsal · Professional",
                "tagline": "60 agents × 96-hour deep rollout + 2 A/B variants (e.g. price points). Includes an explicit comparison verdict on which variant wins.",
                "deliverable_name": "Buyer Reaction & Conversion Friction Report (with A/B)",
                "intake_schema": _ECOMMERCE_INTAKE_EN,
            }},
            report_supplement=(
                "\n【本报告为商业交付物，买家需按交付标准阅读】\n"
                "- 最后一章必须是「行动建议」：给出 3-5 条可在上市前执行的具体动作\n"
                "- 差评风险需按严重程度排序，并指出触发人群与触发条件\n"
                "- 专业版含变量变体：若有变体结果，须单独成章给出「哪个方案更优」的明确结论\n"
            ),
        ),
        Product(
            product_id="ecommerce_launch_dev",
            name="电商新品上市预演 · 开发验证",
            kind=KIND_SIMULATION,
            scenario="ecommerce",
            tagline="内部小预算 SKU：8 Agent × 6 轮，用于端到端验证（不出售）",
            price_cents=0,
            sla_minutes=45,
            deliverable_name="开发验证报告",
            intake_schema=_ECOMMERCE_INTAKE,
            budget={"max_agents": 8, "max_rounds": 6, "variants": 0},
            priority=-10,
            hidden=True,
        ),
        # —— 后续 SKU 占位（inactive，场景包落地后启用）——
        Product(
            product_id="saas_pricing_sandbox",
            i18n={"en": {
                "name": "SaaS Pricing / Redesign Sandbox",
                "tagline": "60 agents (active users, churned users, community KOLs, tech media, competitor) rehearse your pricing change or major redesign: churn risk, acceptance analysis, competitor poaching response.",
                "deliverable_name": "Pricing / Redesign Risk & Acceptance Report",
                "intake_schema": _SAAS_INTAKE_EN,
            }},
            name="SaaS 定价/改版沙盘",
            scenario="saas_pricing",
            tagline="60 个 Agent（在用用户/流失用户/社区KOL/科技媒体/竞品）预演定价调整或大改版后的社区反应与流失风险",
            price_cents=5900,
            sla_minutes=240,
            deliverable_name="定价/改版风险与接受度报告",
            intake_schema={
                "type": "object",
                "required": ["product_name", "pricing_change", "target_users"],
                "properties": {
                    "product_name": {"type": "string", "title": "产品名称", "placeholder": "NoteForge 协作笔记（$12/月 Pro）"},
                    "pricing_change": {"type": "text", "title": "定价/改版方案", "placeholder": "Pro 从 $12/月涨到 $15/月；免费版协作上限从 5 人降到 2 人；新增 AI 功能"},
                    "target_users": {"type": "string", "title": "目标用户", "placeholder": "个人开发者与小团队（5-20人），现有付费用户 3000"},
                    "competitors": {"type": "string", "title": "竞品与替代品", "placeholder": "Notion（$10/月）、Obsidian（免费）", "required": False},
                    "concerns": {"type": "text", "title": "你最担心的风险（可选）", "required": False},
                },
            },
            budget={"max_agents": 60, "max_rounds": 72, "variants": 0},
            priority=12,
            report_supplement=(
                "\n【交付标准】\n"
                "- 流失风险必须按用户群体（免费/个人付费/团队）分别量化\n"
                "- 定价接受度结论必须明确：哪个档位呼声最高、涨价幅度是否超出容忍线\n"
            ),
        ),
        Product(
            product_id="brand_crisis_rehearsal",
            i18n={"en": {
                "name": "Brand Crisis Response Rehearsal",
                "tagline": "60 agents (affected users, bystanders, journalists, regulators, KOLs) rehearse crisis spread and response effectiveness: script A/B, timing choice, second-wave explosion warnings.",
                "deliverable_name": "Crisis Spread & Response Strategy Report",
                "intake_schema": _CRISIS_INTAKE_EN,
            }},
            name="品牌危机回应预演",
            scenario="brand_crisis",
            tagline="60 个 Agent（受影响用户/吃瓜群众/记者/监管/KOL）预演危机传播路径与回应效果：话术 A/B、时点选择、二次引爆点预警",
            price_cents=5900,
            sla_minutes=240,
            deliverable_name="危机传播路径与回应策略报告",
            intake_schema={
                "type": "object",
                "required": ["brand_name", "incident_description"],
                "properties": {
                    "brand_name": {"type": "string", "title": "品牌名称", "placeholder": "星尘科技"},
                    "incident_description": {"type": "text", "title": "危机事件描述", "placeholder": "耳机充电仓过热导致用户手部轻微烫伤，用户已发帖曝光并要求召回，微博讨论量快速上升"},
                    "planned_response": {"type": "text", "title": "品牌准备的回应话术（可给多版做 A/B）", "placeholder": "版本A：4小时内致歉+全额退款+免费换新\n版本B：24小时后公布调查结果+召回", "required": False},
                    "audience": {"type": "string", "title": "受众与传播圈层", "placeholder": "数码圈→微博热搜→财经媒体", "required": False},
                    "concerns": {"type": "text", "title": "你最担心的风险（可选）", "required": False},
                },
            },
            budget={"max_agents": 60, "max_rounds": 72, "variants": 0},
            priority=18,
            report_supplement=(
                "\n【交付标准】\n"
                "- 传播路径必须明确：谁引爆、经谁放大、扩散到哪些圈层\n"
                "- 回应话术效果必须对比回应前后的情绪变化\n"
                "- 二次引爆点预警必须给出触发条件与预防措施\n"
            ),
        ),
        Product(
            product_id="saas_pricing_dev",
            name="SaaS 定价沙盘 · 开发验证",
            kind=KIND_SIMULATION,
            scenario="saas_pricing",
            tagline="内部验证（不出售）",
            price_cents=0,
            sla_minutes=45,
            deliverable_name="开发验证报告",
            intake_schema=_SAAS_INTAKE_EN,
            budget={"max_agents": 8, "max_rounds": 6, "variants": 0},
            priority=-10, hidden=True,
        ),
        Product(
            product_id="brand_crisis_dev",
            name="品牌危机沙盘 · 开发验证",
            kind=KIND_SIMULATION,
            scenario="brand_crisis",
            tagline="内部验证（不出售）",
            price_cents=0,
            sla_minutes=45,
            deliverable_name="开发验证报告",
            intake_schema=_CRISIS_INTAKE_EN,
            budget={"max_agents": 8, "max_rounds": 6, "variants": 0},
            priority=-10, hidden=True,
        ),
        Product(
            product_id="competitor_response_dev",
            name="竞品应对沙盘 · 开发验证",
            kind=KIND_SIMULATION,
            scenario="competitor_response",
            tagline="内部验证（不出售）",
            price_cents=0,
            sla_minutes=45,
            deliverable_name="开发验证报告",
            intake_schema=_COMPETITOR_INTAKE_EN,
            budget={"max_agents": 8, "max_rounds": 6, "variants": 0},
            priority=-10, hidden=True,
        ),
        Product(
            product_id="creator_content_dev",
            name="创作者内容沙盘 · 开发验证",
            kind=KIND_SIMULATION,
            scenario="creator_content",
            tagline="内部验证（不出售）",
            price_cents=0,
            sla_minutes=45,
            deliverable_name="开发验证报告",
            intake_schema=_CREATOR_INTAKE_EN,
            budget={"max_agents": 8, "max_rounds": 6, "variants": 0},
            priority=-10, hidden=True,
        ),
        Product(
            product_id="listing_risk_review",
            i18n={"en": {
                "name": "Cross-border Listing Risk Review",
                "tagline": "5 market & compliance reviewers (US buyer, German buyer, Middle-East buyer, compliance officer, platform policy) audit your listing: cultural sensitivities, regulatory risks, copy rewrites. Delivered in ~5 minutes.",
                "deliverable_name": "Listing Risk Review Report",
                "intake_schema": _LISTING_INTAKE_EN,
            }},
            name="跨境 Listing 风险审查",
            kind=KIND_REVIEW,
            scenario="listing_review",
            tagline="5 位市场/合规评审员（美国买家、德国买家、中东买家、合规官、平台审核）逐项审查：文化敏感点、合规风险、文案优化建议，约 5 分钟交付",
            price_cents=900,
            sla_minutes=15,
            deliverable_name="Listing 风险审查报告",
            intake_schema={
                "type": "object",
                "required": ["listing_title", "listing_description", "target_markets"],
                "properties": {
                    "listing_title": {"type": "string", "title": "Listing 标题", "placeholder": "StarDust Noise-Cancelling Headphones, 60H Battery, CE Certified"},
                    "listing_description": {"type": "text", "title": "Listing 描述（含五点描述）", "placeholder": "• 42dB active noise cancellation\n• 60-hour battery life\n• Premium gift-ready packaging\n• Works with all devices\n• Factory direct price"},
                    "target_markets": {"type": "string", "title": "目标市场（逗号分隔）", "placeholder": "US, Germany, UAE, Japan"},
                    "platform": {"type": "string", "title": "销售平台", "placeholder": "Amazon US / Etsy / Shopify 独立站", "required": False},
                    "product_name": {"type": "string", "title": "产品名称", "required": False},
                },
            },
            budget={},
            priority=5,
            report_supplement=(
                "\n【交付标准】\n"
                "- 高严重度的合规风险必须排在最前，并给出可执行的整改动作\n"
                "- 文案优化建议必须给出改写后的完整标题与五点描述\n"
            ),
        ),
        Product(
            product_id="competitor_response_sandbox",
            i18n={"en": {
                "name": "Competitor Launch Response Sandbox",
                "tagline": "60 agents rehearse the shockwave of your competitor's launch: churn risk, response-action effectiveness, KOL and channel attitudes.",
                "deliverable_name": "Competitor Response Strategy Report",
                "intake_schema": _COMPETITOR_INTAKE_EN,
            }},
            name="竞品发布应对沙盘",
            scenario="competitor_response",
            tagline="60 个 Agent 预演竞品官宣冲击：用户流失风险、我方应对动作效果、KOL 与渠道反应报告",
            price_cents=5900,
            sla_minutes=240,
            deliverable_name="竞品应对策略报告",
            intake_schema={
                "type": "object",
                "required": ["product_name", "competitor_announcement", "target_audience"],
                "properties": {
                    "product_name": {"type": "string", "title": "我方产品", "placeholder": "星尘降噪耳机X（599元）"},
                    "competitor_announcement": {"type": "text", "title": "竞品发布动作", "placeholder": "悦耳AirPro 宣布发布新品 AirPro 2，定价499元，支持空间音频，下周开售"},
                    "our_strengths": {"type": "text", "title": "我方优势与应对资源", "placeholder": "降噪更强、老用户口碑好；可用资源：降价200元/发对比稿/推固件升级", "required": False},
                    "target_audience": {"type": "string", "title": "目标用户", "placeholder": "25-35岁通勤白领"},
                    "concerns": {"type": "text", "title": "你最担心的风险（可选）", "required": False},
                },
            },
            budget={"max_agents": 60, "max_rounds": 72, "variants": 0},
            priority=15,
            report_supplement=(
                "\n【交付标准】\n"
                "- 流失风险必须量化（多少声音明确表示考虑转投、理由分布）\n"
                "- 应对策略结论必须明确：推荐哪种动作组合及理由\n"
            ),
        ),
        Product(
            product_id="creator_content_risk",
            i18n={"en": {
                "name": "Creator Content Risk Rehearsal",
                "tagline": "60 agents (loyal fans, casual viewers, critics, sponsors, platform) rehearse the release of your episode: churn risk, controversy points, brand-safety flags and alternative wording suggestions.",
                "deliverable_name": "Content Risk & Alternative Wording Report",
                "intake_schema": _CREATOR_INTAKE_EN,
            }},
            name="创作者内容风险预演",
            scenario="creator_content",
            tagline="60 个 Agent（铁粉/路人/黑粉/品牌方/平台审核）预演内容发布后的反应：掉粉风险、争议点、品牌安全与替代表达建议",
            price_cents=2900,
            sla_minutes=180,
            deliverable_name="内容风险与替代表达报告",
            intake_schema={
                "type": "object",
                "required": ["product_name", "content_topic", "content_outline"],
                "properties": {
                    "product_name": {"type": "string", "title": "创作者/频道名称", "placeholder": "@TechDaily 数码频道（50万粉丝）"},
                    "content_topic": {"type": "string", "title": "本期内容主题", "placeholder": "「我为什么告别iPhone，全面转向国产折叠屏」"},
                    "content_outline": {"type": "text", "title": "内容大纲/关键表达", "placeholder": "开场吐槽iPhone发热 → 横向对比国产折叠屏 → 承认广告是厂商合作 → 观点：苹果创新停滞"},
                    "audience": {"type": "string", "title": "受众画像", "placeholder": "18-35岁数码爱好者，男性居多，iOS/安卓用户都有", "required": False},
                    "concerns": {"type": "text", "title": "你最担心的风险（可选）", "required": False},
                },
            },
            budget={"max_agents": 60, "max_rounds": 72, "variants": 0},
            priority=8,
            report_supplement=(
                "\n【交付标准】\n"
                "- 掉粉风险必须量化（多少声音明确表示取关/退订，触发原因分布）\n"
                "- 替代表达建议必须逐句给出改写前后对照\n"
                "- 品牌方敏感点需标注哪些内容可能触发撤资\n"
            ),
        ),
    ]


class ProductManager:
    """商品目录管理（JSON 文件持久化）"""

    CATALOG_PATH = os.path.join(Config.UPLOAD_FOLDER, 'products', 'catalog.json')
    _lock = threading.Lock()

    @classmethod
    def _load(cls) -> Dict[str, Any]:
        if os.path.exists(cls.CATALOG_PATH):
            try:
                with open(cls.CATALOG_PATH, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (OSError, ValueError) as e:
                logger.error(f"商品目录文件损坏，将重新播种: {e}")
        return {}

    @classmethod
    def _save(cls, data: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(cls.CATALOG_PATH), exist_ok=True)
        tmp = cls.CATALOG_PATH + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, cls.CATALOG_PATH)

    @classmethod
    def ensure_seeded(cls) -> None:
        with cls._lock:
            data = cls._load()
            if data.get("seed_version") == 6:
                return
            products = {p["product_id"]: p for p in data.get("products", [])}
            for product in _seed_products():
                existing = products.get(product.product_id)
                if existing is not None:
                    # 版本升级：内置字段全量刷新，仅保留用户的支付配置
                    merged = product.to_dict()
                    if existing.get("creem_product_id"):
                        merged["creem_product_id"] = existing["creem_product_id"]
                    products[product.product_id] = merged
                else:
                    products[product.product_id] = product.to_dict()
            cls._save({"seed_version": 6, "products": list(products.values())})
            logger.info("商品目录已播种/更新至 seed_version=6")

    @classmethod
    def get_product(cls, product_id: str) -> Optional[Product]:
        cls.ensure_seeded()
        data = cls._load()
        for item in data.get("products", []):
            if item.get("product_id") == product_id:
                return Product.from_dict(item)
        return None

    @classmethod
    def list_products(cls, include_hidden: bool = False) -> List[Product]:
        cls.ensure_seeded()
        data = cls._load()
        out = []
        for item in data.get("products", []):
            product = Product.from_dict(item)
            if not include_hidden and (product.hidden or not product.active):
                continue
            out.append(product)
        out.sort(key=lambda p: (-p.priority, p.price_cents))
        return out

    @classmethod
    def upsert_product(cls, product: Product) -> None:
        """管理操作：新增/更新一条 SKU（编辑 catalog.json 的编程入口）。"""
        with cls._lock:
            data = cls._load()
            products = {p["product_id"]: p for p in data.get("products", [])}
            products[product.product_id] = product.to_dict()
            cls._save({"seed_version": data.get("seed_version", 1),
                       "products": list(products.values())})
