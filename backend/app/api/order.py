"""订单门户 API。

- 商品目录：GET /api/products
- 订单：POST /api/orders（multipart，含文件）→ GET 列表/详情 → 支付 → 取消
- 交付物：GET /api/orders/<id>/deliverable
- 支付回调：POST /api/orders/stripe/webhook
"""

import json
import os
import shutil
import traceback
import uuid
from datetime import datetime

from flask import request, jsonify, send_file

from . import order_bp
from ..config import Config
from ..models.order import (
    OrderStore,
    STATUS_SUCCEEDED,
)
from ..models.product import ProductManager
from ..services import payment as payment_service
from ..services.report_export import deliverable_path
from ..utils.logger import get_logger
from ..utils.locale import t

logger = get_logger('mirofish.api.order')

_store: OrderStore | None = None

ALLOWED_ORDER_EXTENSIONS = {'pdf', 'md', 'txt', 'markdown'}


def get_store() -> OrderStore:
    global _store
    if _store is None:
        _store = OrderStore()
    return _store


def _allowed_file(filename: str) -> bool:
    ext = os.path.splitext(filename or '')[1].lower().lstrip('.')
    return ext in ALLOWED_ORDER_EXTENSIONS


@order_bp.route('/products', methods=['GET'])
def list_products():
    """商品目录（含 intake_schema，前端动态渲染提交表单）"""
    try:
        include_upcoming = request.args.get('include_upcoming', 'false').lower() == 'true'
        lang = (request.args.get('lang')
                or request.headers.get('Accept-Language', 'zh') or 'zh').split(',')[0].strip()[:2]
        products = ProductManager.list_products()
        out = [p.to_public_dict(language=lang) for p in products]
        if include_upcoming:
            # 即将上线的占位 SKU（coming_soon），前端灰卡展示
            seen = {p.product_id for p in products}
            for p in ProductManager.list_products(include_hidden=True):
                if p.product_id not in seen and p.coming_soon and not p.hidden:
                    d = p.to_public_dict()
                    d["orderable"] = False
                    out.append(d)
        from ..config import Config as _C
        for p in out:
            p.setdefault("orderable", True)
            # 中文界面下附加人民币参考价（实际扣款以 Creem 结算为准）
            p["price_cny_ref"] = round(p["price_cents"] / 100 * _C.USD_TO_CNY_RATE)
        return jsonify({"success": True, "data": out})
    except Exception as e:
        logger.error(f"商品目录读取失败: {e}\n{traceback.format_exc()}")
        return jsonify({"success": False, "error": str(e)}), 500


@order_bp.route('', methods=['POST'])
def create_order():
    """
    提交订单（multipart/form-data）

    字段：
        product_id: SKU（必填）
        user_email: 客户邮箱（必填，交付与订单归属）
        title: 订单标题（可选）
        payload: 提交表单 JSON 字符串（必填，符合 SKU 的 intake_schema）
        files: 种子资料文件（可选，多个）
    """
    try:
        product_id = request.form.get('product_id', '')
        user_email = (request.form.get('user_email') or '').strip()
        title = (request.form.get('title') or '').strip()
        payload_raw = request.form.get('payload', '{}')

        product = ProductManager.get_product(product_id)
        if product is None or not product.active:
            return jsonify({"success": False, "error": "商品不存在或已下架"}), 400
        # hidden SKU（内部验证）仅允许本地开发模式下单，生产环境拦截
        if product.hidden and not Config.ALLOW_DEV_PAYMENT:
            return jsonify({"success": False, "error": "商品不存在或已下架"}), 400
        if not user_email or '@' not in user_email:
            return jsonify({"success": False, "error": "请提供有效的联系邮箱"}), 400

        try:
            payload = json.loads(payload_raw) if payload_raw else {}
        except ValueError:
            return jsonify({"success": False, "error": "payload 必须是合法 JSON"}), 400

        # 表单校验：required 字段
        schema = product.intake_schema or {}
        required = schema.get('required', [])
        missing = [
            field for field in required
            if not str(payload.get(field, '')).strip()
        ]
        if missing:
            return jsonify({
                "success": False,
                "error": f"缺少必填字段: {', '.join(missing)}"
            }), 400

        order_id = f"ord_{uuid.uuid4().hex[:12]}"
        files_dir = os.path.join(Config.UPLOAD_FOLDER, 'orders', order_id, 'files')
        os.makedirs(files_dir, exist_ok=True)

        saved_files = []
        for file in request.files.getlist('files'):
            if not file or not file.filename:
                continue
            if not _allowed_file(file.filename):
                return jsonify({
                    "success": False,
                    "error": f"不支持的文件类型: {file.filename}（支持 pdf/md/txt）"
                }), 400
            safe_name = f"{uuid.uuid4().hex[:8]}{os.path.splitext(file.filename)[1].lower()}"
            path = os.path.join(files_dir, safe_name)
            file.save(path)
            saved_files.append({
                "path": path,
                "original_name": file.filename,
                "size": os.path.getsize(path),
            })

        order = get_store().create(
            order_id=order_id,
            product_id=product.product_id,
            scenario=product.scenario,
            title=title or f"{product.name} · {user_email}",
            user_email=user_email,
            priority=product.priority,
            payload=payload,
            files=saved_files,
        )
        checkout_url = payment_service.create_checkout({
            "order_id": order_id,
            "price_cents": product.price_cents,
            "currency": product.currency,
            "product_name": product.name,
            "title": order.get("title"),
            "creem_product_id": product.creem_product_id,
        })

        return jsonify({
            "success": True,
            "data": {
                **order,
                "checkout_url": checkout_url,
                "payment_mode": payment_service.get_payment_mode(),
            }
        })

    except payment_service.PaymentError as e:
        return jsonify({"success": False, "error": f"支付渠道错误: {e}"}), 502
    except Exception as e:
        logger.error(f"创建订单失败: {e}\n{traceback.format_exc()}")
        return jsonify({"success": False, "error": str(e)}), 500


@order_bp.route('', methods=['GET'])
def list_orders():
    """订单列表。必须按 user_email 过滤（数据隔离）；运维可用 X-Admin-Key 查全部。"""
    try:
        import hmac as hmac_mod
        admin_key = request.headers.get('X-Admin-Key', '')
        if Config.ADMIN_KEY and admin_key and hmac_mod.compare_digest(admin_key, Config.ADMIN_KEY):
            user_email = request.args.get('user_email')
        else:
            user_email = request.args.get('user_email')
            if not user_email or '@' not in user_email:
                return jsonify({
                    "success": False,
                    "error": "必须提供 user_email 查询参数（数据隔离）"
                }), 403
        status = request.args.get('status')
        limit = min(int(request.args.get('limit', 50)), 200)
        orders = get_store().list_orders(user_email=user_email, status=status, limit=limit)
        return jsonify({"success": True, "data": orders})
    except Exception as e:
        logger.error(f"订单列表失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@order_bp.route('/<order_id>', methods=['GET'])
def get_order(order_id: str):
    try:
        order = get_store().get(order_id)
        if order is None:
            return jsonify({"success": False, "error": "订单不存在"}), 404
        return jsonify({"success": True, "data": order})
    except Exception as e:
        logger.error(f"订单查询失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@order_bp.route('/<order_id>/pay', methods=['POST'])
def pay_order(order_id: str):
    """标记订单已支付。dev 模式直接入队；stripe 模式返回 Checkout 地址。"""
    try:
        store = get_store()
        order = store.get(order_id)
        if order is None:
            return jsonify({"success": False, "error": "订单不存在"}), 404

        mode = payment_service.get_payment_mode()
        if mode == payment_service.PAYMENT_MODE_DEV:
            if not Config.ALLOW_DEV_PAYMENT:
                return jsonify({
                    "success": False,
                    "error": "免费支付已被禁用（ALLOW_DEV_PAYMENT 未开启）。"
                             "生产环境请配置 Stripe 或其他支付渠道。"
                }), 403
            if order["status"] != "PENDING_PAYMENT":
                return jsonify({"success": False, "error": f"当前状态 {order['status']} 不可支付"}), 409
            store.mark_paid(order_id)
            return jsonify({
                "success": True,
                "data": {"mode": "dev", "status": "QUEUED",
                         "note": "开发模式：未接入真实支付渠道，直接入队"}
            })

        # stripe / creem 模式：创建/返回 Checkout 地址
        product = ProductManager.get_product(order["product_id"])
        checkout_url = payment_service.create_checkout({
            "order_id": order_id,
            "price_cents": product.price_cents if product else 0,
            "currency": product.currency if product else "usd",
            "product_name": product.name if product else None,
            "title": order.get("title"),
            "creem_product_id": product.creem_product_id if product else None,
        })
        return jsonify({"success": True, "data": {"mode": mode, "checkout_url": checkout_url}})

    except payment_service.PaymentError as e:
        return jsonify({"success": False, "error": f"支付渠道错误: {e}"}), 502
    except Exception as e:
        logger.error(f"支付处理失败: {e}\n{traceback.format_exc()}")
        return jsonify({"success": False, "error": str(e)}), 500


@order_bp.route('/<order_id>/cancel', methods=['POST'])
def cancel_order(order_id: str):
    try:
        ok = get_store().request_cancel(order_id)
        if not ok:
            return jsonify({"success": False, "error": "订单当前状态不可取消"}), 409
        return jsonify({"success": True, "data": get_store().get(order_id)})
    except Exception as e:
        logger.error(f"取消订单失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@order_bp.route('/<order_id>/deliverable', methods=['GET'])
def download_deliverable(order_id: str):
    try:
        order = get_store().get(order_id)
        if order is None:
            return jsonify({"success": False, "error": "订单不存在"}), 404
        if order["status"] != STATUS_SUCCEEDED:
            return jsonify({"success": False, "error": "订单尚未完成交付"}), 409
        email = (request.args.get('email') or '').strip().lower()
        stored_email = (order.get('user_email') or '').lower()
        if stored_email and email != stored_email:
            return jsonify({"success": False, "error": "联系邮箱不匹配"}), 403
        path = deliverable_path(order_id)
        if not os.path.exists(path):
            return jsonify({"success": False, "error": "交付物文件缺失"}), 404
        filename = f"{order.get('title') or order_id}.html"
        return send_file(path, as_attachment=True, download_name=filename)
    except Exception as e:
        logger.error(f"交付物下载失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@order_bp.route('/creem/webhook', methods=['POST'])
def creem_webhook():
    """Creem 支付回调：校验 HMAC 签名后把对应订单标记为已支付。"""
    try:
        payload = request.get_data()
        signature = request.headers.get('creem-signature', '')
        result = payment_service.verify_creem_webhook(payload, signature)
        if result.get("handled") and result.get("order_id"):
            get_store().mark_paid(result["order_id"])
            logger.info(f"Creem 回调入队订单: {result['order_id']}")
        return jsonify({"success": True, "data": result})
    except payment_service.PaymentError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error(f"creem webhook 处理失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 400


@order_bp.route('/stripe/webhook', methods=['POST'])
def stripe_webhook():
    """Stripe 支付回调：校验签名后把对应订单标记为已支付。"""
    try:
        payload = request.get_data()
        signature = request.headers.get('Stripe-Signature', '')
        result = payment_service.verify_stripe_webhook(payload, signature)
        if result.get("handled") and result.get("order_id"):
            get_store().mark_paid(result["order_id"])
            logger.info(f"Stripe 回调入队订单: {result['order_id']}")
        return jsonify({"success": True, "data": result})
    except payment_service.PaymentError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error(f"webhook 处理失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 400
