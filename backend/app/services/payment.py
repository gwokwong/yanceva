"""支付抽象层。

两种模式（PAYMENT_MODE）：
- ``dev``（默认）：无支付渠道，POST /pay 直接标记已支付。仅限本地开发，
  响应中带 ``mode: dev`` 明确标识。
- ``stripe``：Stripe Checkout 托管收银台 + webhook 回调改状态。
  依赖可选安装：``uv sync --extra payments``（stripe 包）。

Worker 只认 QUEUED 状态，支付状态由本层负责流转。
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger('mirofish.payment')

PAYMENT_MODE_DEV = "dev"
PAYMENT_MODE_STRIPE = "stripe"
PAYMENT_MODE_CREEM = "creem"

CREEM_API_BASE = "https://api.creem.io"


def _success_url_with_order(order_id: str) -> str:
    """在 PAYMENT_SUCCESS_URL 上追加 order_id，支付回跳后前端可恢复订单进度页。"""

    url = Config.PAYMENT_SUCCESS_URL
    if not order_id:
        return url
    return url + ("&" if "?" in url else "?") + f"order_id={order_id}"


class PaymentError(RuntimeError):
    """支付渠道配置或调用失败。"""


def get_payment_mode() -> str:
    mode = (Config.PAYMENT_MODE or PAYMENT_MODE_DEV).lower()
    if mode == PAYMENT_MODE_STRIPE and not Config.STRIPE_API_KEY:
        logger.warning("PAYMENT_MODE=stripe 但 STRIPE_API_KEY 未配置，回退 dev 模式")
        return PAYMENT_MODE_DEV
    if mode == PAYMENT_MODE_CREEM and not Config.CREEM_API_KEY:
        logger.warning("PAYMENT_MODE=creem 但 CREEM_API_KEY 未配置，回退 dev 模式")
        return PAYMENT_MODE_DEV
    return mode


def create_checkout(order: Dict[str, Any]) -> Optional[str]:
    """为订单创建支付跳转地址；dev 模式返回 None（直接可标记支付）。"""

    mode = get_payment_mode()
    if mode == PAYMENT_MODE_DEV:
        return None
    success_url = _success_url_with_order(order.get("order_id", ""))

    if mode == PAYMENT_MODE_CREEM:
        creem_product_id = order.get("creem_product_id")
        if not creem_product_id:
            raise PaymentError(
                f"SKU 未配置 Creem 产品 ID（creem_product_id）："
                f"请在 creem.io 后台创建对应产品并填入商品目录"
            )
        import httpx

        try:
            resp = httpx.post(
                f"{CREEM_API_BASE}/v1/checkouts",
                headers={
                    "x-api-key": Config.CREEM_API_KEY or "",
                    "Content-Type": "application/json",
                },
                json={
                    "product_id": creem_product_id,
                    "success_url": success_url,
                    "metadata": {"order_id": order["order_id"]},
                    "request_id": order["order_id"],
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            checkout_url = data.get("checkout_url")
            if not checkout_url:
                raise PaymentError(f"Creem 未返回 checkout_url: {str(data)[:300]}")
            return checkout_url
        except httpx.HTTPStatusError as e:
            detail = getattr(e.response, "text", "")[:300]
            logger.error(f"Creem checkout 创建失败: {detail}")
            raise PaymentError(f"Creem API 错误: {detail}") from e
        except httpx.HTTPError as e:
            logger.error(f"Creem 网络错误: {e}")
            raise PaymentError(f"Creem 网络错误: {e}") from e

    if mode == PAYMENT_MODE_STRIPE:
        try:
            import stripe  # 可选依赖
        except ImportError as e:
            raise PaymentError(
                "未安装 stripe 包：uv sync --extra payments"
            ) from e

        stripe.api_key = Config.STRIPE_API_KEY
        price = order.get("price_cents", 0)
        try:
            session = stripe.checkout.Session.create(
                mode="payment",
                success_url=success_url,
                client_reference_id=order["order_id"],
                metadata={"order_id": order["order_id"]},
                line_items=[{
                    "quantity": 1,
                    "price_data": {
                        "currency": (order.get("currency") or "usd").lower(),
                        "unit_amount": int(price),
                        "product_data": {
                            "name": order.get("product_name") or order.get("title") or "预演服务",
                        },
                    },
                }],
            )
            return session.url
        except Exception as e:  # noqa: BLE001 - 渠道错误统一转译
            logger.error(f"Stripe Checkout 创建失败: {e}")
            raise PaymentError(str(e)) from e

    raise PaymentError(f"未知支付模式: {mode}")


def verify_creem_webhook(payload: bytes, signature: str) -> Dict[str, Any]:
    """校验 Creem webhook（creem-signature = HMAC-SHA256(raw body, secret)）

    并解析出订单号：仅处理 ``checkout.completed`` 事件且
    ``metadata.order_id`` 命中的回调。
    """
    import hashlib
    import hmac as hmac_mod

    if not Config.CREEM_WEBHOOK_SECRET:
        raise PaymentError("CREEM_WEBHOOK_SECRET 未配置")

    expected = hmac_mod.new(
        Config.CREEM_WEBHOOK_SECRET.encode("utf-8"), payload, hashlib.sha256
    ).hexdigest()
    if not signature or not hmac_mod.compare_digest(expected, signature.strip()):
        raise PaymentError("Creem webhook 签名校验失败")

    try:
        event = json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise PaymentError(f"webhook 载荷解析失败: {e}") from e

    event_type = event.get("type", "") if isinstance(event, dict) else ""
    obj = event.get("object", {}) or {} if isinstance(event, dict) else {}
    metadata = obj.get("metadata", {}) or {}
    order_id = metadata.get("order_id")

    if event_type == "checkout.completed" and order_id:
        return {"handled": True, "order_id": order_id, "event_type": event_type}
    return {"handled": False, "order_id": order_id, "event_type": event_type}


def verify_stripe_webhook(payload: bytes, signature: str) -> Dict[str, Any]:
    """校验并解析 Stripe webhook 事件（仅接受 payment_intent.succeeded /
    checkout.session.completed 且 metadata.order_id 命中的事件）。"""

    if not Config.STRIPE_WEBHOOK_SECRET:
        raise PaymentError("STRIPE_WEBHOOK_SECRET 未配置")
    try:
        import stripe
    except ImportError as e:
        raise PaymentError("未安装 stripe 包：uv sync --extra payments") from e

    stripe.api_key = Config.STRIPE_API_KEY
    event = stripe.Webhook.construct_event(
        payload, signature, Config.STRIPE_WEBHOOK_SECRET
    )
    event_type = event.get("type", "")
    if event_type not in ("checkout.session.completed", "payment_intent.succeeded"):
        return {"handled": False, "order_id": None, "event_type": event_type}

    obj = event.get("data", {}).get("object", {}) or {}
    order_id = obj.get("metadata", {}).get("order_id") or obj.get("client_reference_id")
    return {"handled": True, "order_id": order_id, "event_type": event_type}
