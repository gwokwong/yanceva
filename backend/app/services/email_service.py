"""邮件通知服务：订单完成后发送交付通知。

使用 Resend API（https://resend.com，免费 100 封/天）。
未配置 RESEND_API_KEY 时静默跳过（本地开发不阻塞）。

配置（.env）：
    RESEND_API_KEY=re_xxxxxxxx
    RESEND_FROM_EMAIL=noreply@yanceva.com   # 需在 Resend 后台验证域名
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger('mirofish.email')


def is_configured() -> bool:
    return bool(Config.RESEND_API_KEY)


def send_order_completed(
    *,
    order_id: str,
    user_email: str,
    title: str,
    deliverable_url: str,
    report_url: str = "",
    language: str = "zh",
    metrics_summary: Optional[Dict[str, Any]] = None,
) -> bool:
    """发送订单完成通知邮件。

    Returns:
        True = 发送成功；False = 未配置或发送失败（不影响订单状态）。
    """
    if not is_configured():
        logger.info(f"邮件未配置（RESEND_API_KEY 缺失），跳过发送: {order_id}")
        return False

    from_url = Config.RESEND_FROM_EMAIL or "onboarding@resend.dev"
    templates = _EMAIL_TEMPLATES.get(language if language in _EMAIL_TEMPLATES else "zh")
    subject = templates["subject"].format(title=title)

    report_link_html = ""
    if report_url:
        report_label = "在线交互报告" if language == "zh" else "Interactive Report"
        report_link_html = (
            f'<p style="text-align:center;margin:8px 0;">'
            f'<a href="{report_url}" style="color:#FF4500;font-size:13px;">{report_label}</a></p>'
        )

    html = templates["html"].format(
        title=title,
        order_id=order_id,
        deliverable_url=deliverable_url,
        report_url=report_url,
        report_link=report_link_html,
        disclaimer=templates["disclaimer"],
        cta=templates["cta"],
    )

    try:
        import httpx

        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {Config.RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": from_url,
                "to": [user_email],
                "subject": subject,
                "html": html,
            },
            timeout=30,
        )
        resp.raise_for_status()
        logger.info(f"邮件已发送: {order_id} → {user_email}")
        return True
    except Exception as e:
        logger.warning(f"邮件发送失败（不影响订单）: {order_id}, {e}")
        return False


_EMAIL_TEMPLATES = {
    "zh": {
        "subject": "推演完成 · {title}",
        "disclaimer": "推演结果为模拟预测，不构成对真实市场结果的保证。",
        "cta": "下载交付报告",
        "html": """
<div style="font-family:'PingFang SC','Microsoft YaHei',sans-serif;max-width:560px;margin:0 auto;color:#1a1a1a;">
  <div style="border-bottom:3px solid #FF4500;padding-bottom:16px;margin-bottom:24px;">
    <div style="color:#FF9B6A;letter-spacing:3px;font-size:13px;font-weight:800;">YANCEVA · REHEARSAL PLATFORM</div>
    <h1 style="font-size:22px;margin:8px 0 0;">您的推演已完成</h1>
  </div>
  <p>订单 <b>{order_id}</b>「{title}」的推演已全部完成。</p>
  <p>点击下方按钮查看并下载交付报告：</p>
  <p style="text-align:center;margin:28px 0;">
    <a href="{deliverable_url}" style="background:#FF4500;color:#fff;padding:12px 36px;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px;">{cta}</a>
  </p>
  {report_link}
  <p style="margin-top:24px;font-size:12px;color:#999;">{disclaimer}</p>
  <div style="border-top:1px solid #eee;margin-top:24px;padding-top:12px;font-size:11px;color:#aaa;">
    Yanceva Rehearsal Platform · Order {order_id}
  </div>
</div>""",
    },
    "en": {
        "subject": "Rehearsal Complete · {title}",
        "disclaimer": "Rehearsal results are simulated predictions, not guarantees of real-world outcomes.",
        "cta": "Download Report",
        "html": """
<div style="font-family:'Space Grotesk',sans-serif;max-width:560px;margin:0 auto;color:#1a1a1a;">
  <div style="border-bottom:3px solid #FF4500;padding-bottom:16px;margin-bottom:24px;">
    <div style="color:#FF9B6A;letter-spacing:3px;font-size:13px;font-weight:800;">YANCEVA · REHEARSAL PLATFORM</div>
    <h1 style="font-size:22px;margin:8px 0 0;">Your rehearsal is complete</h1>
  </div>
  <p>Order <b>{order_id}</b> "{title}" has finished all simulation stages.</p>
  <p>Click below to view and download your deliverable report:</p>
  <p style="text-align:center;margin:28px 0;">
    <a href="{deliverable_url}" style="background:#FF4500;color:#fff;padding:12px 36px;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px;">{cta}</a>
  </p>
  {report_link}
  <p style="margin-top:24px;font-size:12px;color:#999;">{disclaimer}</p>
  <div style="border-top:1px solid #eee;margin-top:24px;padding-top:12px;font-size:11px;color:#aaa;">
    Yanceva Rehearsal Platform · Order {order_id}
  </div>
</div>""",
    },
}
