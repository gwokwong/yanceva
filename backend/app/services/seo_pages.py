"""SEO 预渲染服务：为关键路由生成静态 HTML（双语），供爬虫/AI 引擎抓取。

问题：SPA 的内容在客户端渲染，Google 能执行 JS 但 AI 爬虫（GPTBot/ClaudeBot/
PerplexityBot）和部分搜索引擎不能——它们看到的是空 <div id="app">。

方案：启动时从 locales/*.json 生成每路由双语静态 HTML（内容完整的落地页/
订单门户/隐私/条款快照），Flask 在识别到爬虫 UA 或 ?_pre=1 时优先返回静态版。

- 爬虫拿到完整内容 → 可索引、可被 AI 引用
- 人类浏览器拿到正常 SPA → 交互不受影响
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger('mirofish.seo_pages')

_LOCALES_DIR = Path(Config.UPLOAD_FOLDER).parent.parent / 'locales'
_ROUTES = ['/', '/orders', '/rehearse', '/privacy', '/terms']


def _load_locale(lang: str) -> Dict[str, Any]:
    try:
        return json.loads((_LOCALES_DIR / f'{lang}.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def _tr(messages: Dict[str, Any], dotted: str, fallback: str = '') -> str:
    """按 dotted key 取 i18n 值。"""
    cur: Any = messages
    for part in dotted.split('.'):
        if not isinstance(cur, dict) or part not in cur:
            return fallback
        cur = cur[part]
    return str(cur) if cur is not None else fallback


_PRICING = [
    ("E-commerce Launch Rehearsal · Professional", 59, "60 agents × 96-hour rollout + 2 A/B variants with comparison verdict."),
    ("Brand Crisis Response Rehearsal", 59, "Crisis spread path, response script A/B, second-wave explosion warnings."),
    ("Competitor Launch Response Sandbox", 59, "Competitor shockwave simulation: churn risk, response-action effectiveness."),
    ("SaaS Pricing / Redesign Sandbox", 59, "Pricing change or redesign simulation: churn risk, acceptance analysis."),
    ("E-commerce Launch Rehearsal · Standard", 29, "40 agents, 48-hour rollout. Buyer reaction, review risks, competitor response."),
    ("Creator Content Risk Rehearsal", 29, "Episode release simulation: churn risk, controversy points, brand safety."),
    ("Cross-border Listing Risk Review", 9, "5 market & compliance reviewers audit your listing in ~5 minutes."),
]

_FAQS = [
    ("How reliable are the results?",
     "Every conclusion comes from conversations that actually happened inside the simulation, with verbatim quotes and quantified metrics. It is a prediction aid, not a guarantee."),
    ("What do I get and when?",
     "A report with volume/sentiment/purchase-intent charts, verbatim agent quotes and action items. Standard ~2 hours; Professional with A/B variants ~4 hours."),
    ("Is my product data safe?",
     "Your materials are used only to run your rehearsal. The LLM provider's policy states customer data is not used for training. You can request deletion at any time."),
    ("What scenarios are available?",
     "Six live scenarios: e-commerce launch, SaaS pricing, brand crisis, listing review, competitor response, creator content risk."),
    ("How much does it cost?",
     "Sandbox rehearsals from $29, listing review from $9, professional tier with A/B variants $59."),
]


def _page_html(lang: str, route: str) -> str:
    """生成单页静态 HTML。"""
    m = _load_locale(lang)
    site = "https://yanceva.com"

    if route == '/':
        title = "Yanceva | AI Business Rehearsal Platform — Simulate Decisions Before You Commit"
        desc = ("Rehearse business decisions on a sandbox of AI agents. Product launches, "
                "SaaS pricing, brand crises, listing reviews, competitor moves — "
                "actionable reports in hours.")
        h1 = _tr(m, 'landing.heroTitle', 'Rehearse business decisions in a sandbox of AI agents')
        body_intro = _tr(m, 'landing.heroSub')

        pricing_rows = ''.join(
            f'<tr><td>{name}</td><td>${price}</td><td>{desc}</td></tr>'
            for name, price, desc in _PRICING
        )
        faq_items = ''.join(
            f'<h3>{q}</h3><p>{a}</p>' for q, a in _FAQS
        )

        content = f'''
<h2>Services & Pricing</h2>
<table>
<tr><th>Service</th><th>Price (USD)</th><th>Description</th></tr>
{pricing_rows}
</table>
<h2>How it works</h2>
<ol>
<li><b>Describe the scenario</b> — fill a short form, upload docs (optional)</li>
<li><b>60 agents simulate your market</b> — buyers, critics, competitors, journalists with unique personas</li>
<li><b>Get your decision report</b> — quantified metrics, verbatim quotes, action items</li>
</ol>
<h2>Frequently Asked Questions</h2>
{faq_items}
'''
    elif route == '/orders':
        title = "Order a Rehearsal | Yanceva"
        desc = "Choose a rehearsal service and order online. Delivery in hours."
        h1 = "Choose a Rehearsal Service"
        content = '<p>' + _tr(m, 'landing.heroSub') + '</p>'
    elif route == '/rehearse':
        title = "Rehearsal Workspace | Yanceva"
        desc = "Interactive rehearsal workspace: graph build, agent simulation, report generation."
        h1 = "Rehearsal Workspace"
        content = '<p>' + _tr(m, 'landing.heroSub') + '</p>'
    else:
        return _legal_html(lang, route)

    json_ld = f'''<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"WebPage","name":"{_escape(title)}","url":"{site}{route}","description":"{_escape(desc)}"}}</script>'''

    return f'''<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<title>{_escape(title)}</title>
<meta name="description" content="{_escape(desc)}">
<link rel="canonical" href="{site}{route}">
<meta name="robots" content="index, follow">
{json_ld}
</head>
<body>
<header><strong>Yanceva</strong> — AI Business Rehearsal Platform</header>
<main>
<h1>{_escape(h1)}</h1>
<p>{_escape(body_intro)}</p>
{content}
</main>
<footer><p>© 2026 Yanceva · Powered by <a href="https://github.com/666ghj/MiroFish">MiroFish</a> (AGPL-3.0)</p></footer>
</body>
</html>'''


def _legal_html(lang: str, route: str) -> str:
    """法律页面（内容较长，从 Vue 组件同源数据生成精简版）。"""
    if route == '/privacy':
        title = "Privacy Policy | Yanceva"
        body = ("We collect your contact email, uploaded materials, order records and simulation "
                "artifacts. Data is sent to our LLM provider (DeepSeek, no training on customer "
                "data) and payments handled by Creem (Merchant of Record). You may request "
                "deletion at any time via gwokwong@gmail.com.")
    else:
        title = "Terms of Service | Yanceva"
        body = ("AI multi-agent sandbox rehearsals. Results are simulated predictions, not "
                "guarantees. Deliverables are licensed for internal business decision-making. "
                "Liability capped at the order amount. Materials treated as confidential.")

    site = "https://yanceva.com"
    return f'''<!DOCTYPE html>
<html lang="{lang}">
<head><meta charset="utf-8"><title>{_escape(title)}</title>
<meta name="description" content="{_escape(body[:150])}">
<link rel="canonical" href="{site}{route}">
<meta name="robots" content="noindex, follow">
</head>
<body>
<header><strong>Yanceva</strong></header>
<main><h1>{_escape(title)}</h1><p>{_escape(body)}</p>
<p>Contact: <a href="mailto:gwokwong@gmail.com">gwokwong@gmail.com</a></p></main>
<footer><p>© 2026 Yanceva</p></footer>
</body></html>'''


def _escape(s: str) -> str:
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def generate_all(output_dir: Path) -> int:
    """生成全部静态页（双语目录结构 /en/ /zh/ + 根英文）。"""
    count = 0
    for lang, prefix in (('en', ''), ('zh', '/zh')):
        for route in _ROUTES:
            html = _page_html(lang, route)
            # /privacy /terms 是 noindex，仍生成（hreflang 指向）
            dir_ = output_dir / prefix.lstrip('/') if prefix else output_dir
            route_file = route if route != '/' else ''
            page_dir = dir_ / route_file.lstrip('/') if route_file else dir_
            page_dir.mkdir(parents=True, exist_ok=True)
            (page_dir / 'index.html').write_text(html, encoding='utf-8')
            count += 1
    return count


def is_crawler(user_agent: str) -> bool:
    """识别爬虫 UA（Google/AI 引擎/主流搜索）。"""
    if not user_agent:
        return False
    ua = user_agent.lower()
    keywords = (
        'googlebot', 'bingbot', 'yandexbot', 'duckduckbot', 'baiduspider',
        'gptbot', 'claudebot', 'anthropic', 'perplexitybot', 'ccbot',
        'applebot', 'slurp', 'facebookexternalhit', 'twitterbot',
        'linkedinbot', 'bytespider',
    )
    return any(k in ua for k in keywords)
