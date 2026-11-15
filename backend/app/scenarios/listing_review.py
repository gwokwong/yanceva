"""跨境电商多语言 Listing 风险审查场景（轻量评审单）。

不走多智能体模拟：由多国 persona 组成的评审团对 Listing 文案做结构化
评审（文化敏感点 / 合规风险 / 平台规则 / 转化优化），产出审查报告。
"""

from .base import Scenario

# ── 评审团面板（每个成员一次独立 LLM 评审调用）────────────────
REVIEW_PANEL = [
    {
        "id": "us_buyer",
        "name": "US buyer (mom, 35, Amazon Prime habit)",
        "persona": "A practical American online shopper, 35, buys everything on Amazon. Skims listings fast, allergic to hype, cares about price-value clarity, shipping expectations and review counts.",
        "focus": "clarity of value proposition, trust signals, appeal to US buyers",
    },
    {
        "id": "eu_buyer",
        "name": "German buyer (precision-oriented)",
        "persona": "A German engineer, 40, skeptical of marketing claims. Expects precise specs (dimensions, materials, certifications), dislikes superlatives without evidence, cares about CE marking, sustainability and returns policy.",
        "focus": "spec completeness, evidence for claims, EU expectations",
    },
    {
        "id": "me_buyer",
        "name": "Middle East buyer (premium gift shopper)",
        "persona": "A buyer from UAE, 30, shops for premium gifts. Cares about gift-readiness, premium presentation, and culturally appropriate imagery/wording (e.g. religious symbols, alcohol references, hand gestures).",
        "focus": "premium perception, cultural appropriateness, gift appeal",
    },
    {
        "id": "compliance",
        "name": "Cross-border compliance officer",
        "persona": "A cross-border e-commerce compliance specialist. Checks restricted claims (FDA/FCC/CE, 'medical grade', 'cure/treat'), banned superlatives, safety certifications, country-specific import restrictions, and IP/trademark red flags.",
        "focus": "regulatory claim risks, certification requirements, restricted words",
    },
    {
        "id": "platform_policy",
        "name": "Marketplace policy reviewer (Amazon/Etsy/Shopify)",
        "persona": "A former marketplace trust-&-safety reviewer. Flags keyword stuffing, review solicitation wording, prohibited claims, category mis-placement, trademark misuse in titles, and bullet-format violations.",
        "focus": "listing format rules, prohibited content, search-quality",
    },
]

REVIEW_SYSTEM_PROMPT = (
    "You are a cross-border e-commerce listing reviewer playing the following role:\n"
    "{persona}\n\n"
    "Review the listing copy from your role's perspective. Respond ONLY with a JSON object:\n"
    '{{"scores": {{"overall": <1-10>, "appeal": <1-10>, "trust": <1-10>}}, '
    '"risks": [{{"type": "cultural"|"compliance"|"platform_policy"|"conversion"|"other", '
    '"severity": "high"|"medium"|"low", "quote": "<the exact problematic phrase>", '
    '"issue": "<why it is a problem for your market>", '
    '"suggestion": "<a concrete rewrite or fix>"}}], '
    '"highlights": ["<what works well>"], '
    '"verdict": "<one-paragraph overall impression>"}}\n'
    "Focus on: {focus}. Find real issues; if the copy is clean, say so honestly with fewer risks. "
    "Write issue/suggestion/verdict in the listing's own language or English."
)

REVIEW_SYNTHESIS_PROMPT = (
    "You are the lead consultant of a cross-border listing risk review. You are given the "
    "original listing and the structured reviews from a panel of market/compliance reviewers.\n\n"
    "Write the final review report in Markdown with these sections:\n"
    "1. **Overall Assessment** — 2-3 sentence verdict + a risk-level rating (low/medium/high)\n"
    "2. **Top Risks (sorted by severity)** — a table: quote / market / issue / suggested fix; "
    "highlight any high-severity compliance items first\n"
    "3. **Cultural Sensitivity Notes** — per target market\n"
    "4. **Compliance Checklist** — claims/certifications to verify before publishing\n"
    "5. **Copy Optimization Suggestions** — rewritten title + bullets (the strongest version)\n"
    "6. **Action Items** — 3-5 concrete steps before publishing\n\n"
    "Quote real phrases from the listing when discussing issues. Be specific, not generic.\n\n"
    "=== ORIGINAL LISTING ===\n{listing}\n\n"
    "=== PANEL REVIEWS ===\n{reviews}\n\n"
    "Write the report in {language}."
)


LISTING_REVIEW_SCENARIO = Scenario(
    name="listing_review",
    label_key="home.scenarioLabelListingReview",
    description_key="home.scenarioDescListingReview",
    # 评审单不走本体/图谱/模拟——以下字段仅满足接口，不会被调用
    ontology_system_prompt="[review kind: ontology not used]",
    ontology_user_rules="",
    persona_system_prompt="[review kind: personas are the review panel]",
    individual_persona_prompt="{entity_name}",
    group_persona_prompt="{entity_name}",
    individual_entity_types=(),
    group_entity_types=(),
    knowledge_node_types=(),
    default_max_agents=0,
    report_plan_supplement="",
    report_section_supplement="",
)
