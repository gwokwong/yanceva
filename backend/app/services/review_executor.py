"""评审单执行器（Listing 风险审查等轻量服务）。

不走多智能体模拟：多国 persona 评审团对客户提交的文案做结构化评审，
汇总成审查报告并生成交付物。无 Neo4j/OASIS 依赖，几分钟交付。
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..scenarios.listing_review import (
    REVIEW_PANEL,
    REVIEW_SYSTEM_PROMPT,
    REVIEW_SYNTHESIS_PROMPT,
)
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger

logger = get_logger('mirofish.review_executor')


def _parse_json_object(text: str) -> Dict[str, Any]:
    """从 LLM 返回中提取首个 JSON 对象（容忍代码块与尾巴文本）。"""
    import json

    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    idx = text.find("{")
    if idx == -1:
        raise ValueError(f"响应中未找到 JSON 对象: {text[:200]}")
    import json as _json

    obj, _end = _json.JSONDecoder().raw_decode(text[idx:])
    return obj


def run_review(
    *,
    requirement: str,
    payload: Dict[str, Any],
    language: str = "en",
    progress_callback=None,
    extra_context: str = "",
) -> Dict[str, Any]:
    """执行一次评审：评审团逐个调用 → 综合报告。

    Returns:
        {"report_markdown": ..., "panel_reviews": [...], "overall_score": ...}
    """

    llm = LLMClient(timeout=180.0)

    listing_parts = [
        f"### {key}\n{value}" for key, value in payload.items() if value
    ]
    if extra_context:
        listing_parts.append(f"### Supporting materials uploaded by the seller\n{extra_context[:6000]}")
    listing = "\n\n".join(listing_parts) or requirement

    total = len(REVIEW_PANEL)
    panel_reviews: List[Dict[str, Any]] = []
    for idx, member in enumerate(REVIEW_PANEL):
        if progress_callback:
            progress_callback(f"reviewer {member['id']} ({idx + 1}/{total})", (idx) / total)
        prompt = REVIEW_SYSTEM_PROMPT.format(
            persona=member["persona"], focus=member["focus"]
        )
        try:
            raw = llm.chat(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": f"=== LISTING ===\n{listing}"},
                ],
                temperature=0.4,
                max_tokens=2048,
            )
            review = _parse_json_object(raw)
            review["reviewer_id"] = member["id"]
            review["reviewer_name"] = member["name"]
            panel_reviews.append(review)
        except Exception as e:  # noqa: BLE001 - 单个评审失败不阻断整体
            logger.warning(f"评审成员 {member['id']} 失败: {e}")
            panel_reviews.append({
                "reviewer_id": member["id"],
                "reviewer_name": member["name"],
                "verdict": f"(review failed: {e})",
                "risks": [],
                "scores": {"overall": None, "appeal": None, "trust": None},
            })
    if progress_callback:
        progress_callback(f"panel done ({total}/{total})", 1.0)

    # ── 综合报告 ──────────────────────────────────────────────
    if progress_callback:
        progress_callback("synthesis", 1.0)
    reviews_text = "\n\n".join(
        f"### Reviewer: {r.get('reviewer_name')}\n"
        f"Scores: {r.get('scores')}\nVerdict: {r.get('verdict')}\n"
        + "\n".join(
            f"- [{risk.get('severity')}/{risk.get('type')}] \"{risk.get('quote', '')}\" "
            f"→ {risk.get('issue')} → Fix: {risk.get('suggestion')}"
            for risk in (r.get("risks") or [])
        )
        for r in panel_reviews
    )
    lang_name = "Chinese (中文)" if (language or "zh").lower().startswith("zh") else "English"
    report_markdown = llm.chat(
        messages=[
            {"role": "user", "content": REVIEW_SYNTHESIS_PROMPT.format(
                listing=listing, reviews=reviews_text, language=lang_name)},
        ],
        temperature=0.4,
        max_tokens=4096,
    )

    scored = [
        r.get("scores", {}).get("overall")
        for r in panel_reviews
        if isinstance(r.get("scores", {}).get("overall"), (int, float))
    ]
    overall = round(sum(scored) / len(scored), 1) if scored else None

    return {
        "report_markdown": report_markdown,
        "panel_reviews": panel_reviews,
        "overall_score": overall,
    }
