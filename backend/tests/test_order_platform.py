"""平台订单系统测试：商品目录 / 订单存储 / 支付模式 / API。"""

import json
import os

import pytest
from flask import Flask

from app.config import Config
from app.models.order import (
    STATUS_ASSIGNED,
    STATUS_CANCELLED,
    STATUS_FAILED,
    STATUS_PENDING_PAYMENT,
    STATUS_QUEUED,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    OrderStore,
)
from app.models.product import ProductManager, KIND_SIMULATION
from app.worker import compile_requirement


@pytest.fixture()
def order_store(tmp_path):
    return OrderStore(db_path=os.path.join(str(tmp_path), "orders.db"))


@pytest.fixture()
def isolated_catalog(tmp_path, monkeypatch):
    monkeypatch.setattr(
        ProductManager, "CATALOG_PATH",
        os.path.join(str(tmp_path), "products", "catalog.json"),
    )
    ProductManager.ensure_seeded()
    return tmp_path


# ============== 商品目录 ==============

def test_catalog_seeds_public_skus(isolated_catalog):
    products = ProductManager.list_products()
    ids = [p.product_id for p in products]
    assert "ecommerce_launch_std" in ids
    assert "ecommerce_launch_pro" in ids
    assert "ecommerce_launch_dev" not in ids   # 开发 SKU 不对外
    assert "saas_pricing_sandbox" in ids       # 全场景已激活
    assert "listing_risk_review" in ids


def test_sku_has_intake_schema_and_budget(isolated_catalog):
    product = ProductManager.get_product("ecommerce_launch_std")
    assert product.kind == KIND_SIMULATION
    assert product.scenario == "ecommerce"
    required = product.intake_schema.get("required", [])
    assert "product_name" in required and "launch_plan" in required
    assert product.budget["max_agents"] == 40
    assert product.price_cents == 4900


def test_dev_sku_hidden_but_retrievable(isolated_catalog):
    assert ProductManager.get_product("ecommerce_launch_dev") is not None
    public = [p.product_id for p in ProductManager.list_products()]
    assert "ecommerce_launch_dev" not in public


# ============== 订单存储生命周期 ==============

def _create(store, **kwargs):
    return store.create(
        order_id=kwargs.get("order_id", "ord_test1"),
        product_id=kwargs.get("product_id", "ecommerce_launch_std"),
        scenario="ecommerce",
        title="测试订单",
        user_email="buyer@example.com",
        priority=10,
        payload={"product_name": "耳机X"},
        files=[{"path": "/tmp/a.txt", "original_name": "a.txt"}],
    )


def test_order_lifecycle_happy_path(order_store):
    order = _create(order_store)
    assert order["status"] == STATUS_PENDING_PAYMENT
    assert order["payload"]["product_name"] == "耳机X"

    assert order_store.mark_paid("ord_test1") is True
    assert order_store.get("ord_test1")["status"] == STATUS_QUEUED

    claimed = order_store.claim_next("worker_a")
    assert claimed["order_id"] == "ord_test1"
    assert claimed["status"] == STATUS_ASSIGNED
    assert claimed["worker_id"] == "worker_a"

    order_store.mark_running("ord_test1")
    assert order_store.get("ord_test1")["status"] == STATUS_RUNNING

    order_store.update_progress("ord_test1", 42, "graph", "图谱摄取 60%")
    order = order_store.get("ord_test1")
    assert order["progress"] == 42
    assert "graph" in order["stage_detail"]

    order_store.set_result("ord_test1", {"report_id": "report_x"})
    order = order_store.get("ord_test1")
    assert order["status"] == STATUS_SUCCEEDED
    assert order["progress"] == 100
    assert order["result"]["report_id"] == "report_x"


def test_claim_skips_unpaid_orders(order_store):
    _create(order_store)
    assert order_store.claim_next("worker_a") is None  # 未支付不可认领
    order_store.mark_paid("ord_test1")
    claimed = order_store.claim_next("worker_a")
    assert claimed is not None


def test_claim_is_atomic_no_double_assignment(order_store):
    order_store.create(order_id="ord_a", product_id="p", scenario="ecommerce", paid=True)
    order_store.create(order_id="ord_b", product_id="p", scenario="ecommerce", paid=True)
    first = order_store.claim_next("worker_a")
    second = order_store.claim_next("worker_b")
    assert first["order_id"] != second["order_id"]
    third = order_store.claim_next("worker_c")
    assert third is None


def test_claim_respects_priority_then_fifo(order_store):
    for oid, priority in [("low", 0), ("high", 50), ("mid", 10)]:
        order_store.create(order_id=oid, product_id="p", scenario="ecommerce",
                           priority=priority, paid=True)
    claimed = order_store.claim_next("w")
    assert claimed["order_id"] == "high"
    claimed = order_store.claim_next("w")
    assert claimed["order_id"] == "mid"


def test_cancel_before_claim(order_store):
    _create(order_store)
    order_store.mark_paid("ord_test1")
    assert order_store.request_cancel("ord_test1") is True
    assert order_store.get("ord_test1")["status"] == STATUS_CANCELLED
    assert order_store.claim_next("worker_a") is None


def test_cancel_during_execution_sets_flag(order_store):
    _create(order_store)
    order_store.mark_paid("ord_test1")
    order_store.claim_next("worker_a")
    order_store.mark_running("ord_test1")
    assert order_store.request_cancel("ord_test1") is True
    assert order_store.is_cancel_requested("ord_test1") is True
    # 终态仍由 worker 协作停止后标记
    order_store.mark_cancelled("ord_test1")
    assert order_store.get("ord_test1")["status"] == STATUS_CANCELLED


def test_failed_order_records_error(order_store):
    _create(order_store)
    order_store.mark_paid("ord_test1")
    order_store.claim_next("worker_a")
    order_store.set_failed("ord_test1", "模拟超时")
    order = order_store.get("ord_test1")
    assert order["status"] == STATUS_FAILED
    assert "超时" in order["error"]


# ============== 需求编译 ==============

def test_compile_requirement_ecommerce():
    requirement = compile_requirement("ecommerce", {
        "product_name": "星尘耳机X",
        "price_point": "599元",
        "target_audience": "通勤白领",
        "launch_plan": "第7天首销",
    })
    assert "星尘耳机X" in requirement
    assert "599元" in requirement
    assert "上市计划" in requirement


# ============== 支付模式 ==============

def test_payment_mode_defaults_to_dev(monkeypatch):
    from app.services import payment
    monkeypatch.setattr(Config, "PAYMENT_MODE", "dev")
    assert payment.get_payment_mode() == payment.PAYMENT_MODE_DEV
    assert payment.create_checkout({"order_id": "ord_x"}) is None


def test_payment_mode_stripe_requires_key(monkeypatch):
    from app.services import payment
    monkeypatch.setattr(Config, "PAYMENT_MODE", "stripe")
    monkeypatch.setattr(Config, "STRIPE_API_KEY", None)
    assert payment.get_payment_mode() == payment.PAYMENT_MODE_DEV  # 回退


# ============== 订单 API ==============

@pytest.fixture()
def order_app(tmp_path, monkeypatch, isolated_catalog):
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
    from app.api import order as order_api
    monkeypatch.setattr(order_api, "_store", None)  # 重置单例
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(order_api.order_bp, url_prefix="/api/orders")
    return app.test_client()


def _submit_order(client, product_id="ecommerce_launch_std"):
    return client.post("/api/orders", data={
        "product_id": product_id,
        "user_email": "buyer@example.com",
        "title": "耳机上市预演",
        "payload": json.dumps({
            "product_name": "星尘耳机X", "price_point": "599元",
            "target_audience": "通勤白领", "launch_plan": "第7天首销",
        }),
    }, content_type="multipart/form-data")


def test_api_products_lists_public_catalog(order_app):
    res = order_app.get("/api/orders/products")
    assert res.status_code == 200
    body = res.get_json()
    ids = [p["product_id"] for p in body["data"]]
    assert "ecommerce_launch_std" in ids
    assert body["data"][0]["intake_schema"]["required"]


def test_api_create_order_missing_required_field(order_app):
    res = order_app.post("/api/orders", data={
        "product_id": "ecommerce_launch_std",
        "user_email": "buyer@example.com",
        "payload": json.dumps({"product_name": "只有名字"}),
    }, content_type="multipart/form-data")
    assert res.status_code == 400
    assert "缺少必填字段" in res.get_json()["error"]


def test_api_create_pay_and_status_flow(order_app, tmp_path):
    res = _submit_order(order_app)
    assert res.status_code == 200
    body = res.get_json()["data"]
    order_id = body["order_id"]
    assert body["status"] == STATUS_PENDING_PAYMENT
    assert body["payment_mode"] == "dev"
    assert body["checkout_url"] is None

    res = order_app.post(f"/api/orders/{order_id}/pay")
    assert res.status_code == 200
    assert res.get_json()["data"]["status"] == "QUEUED"

    order = order_app.get(f"/api/orders/{order_id}").get_json()["data"]
    assert order["status"] == STATUS_QUEUED
    assert order["files"] == []


def test_api_deliverable_blocked_until_succeeded(order_app):
    res = _submit_order(order_app)
    order_id = res.get_json()["data"]["order_id"]
    res = order_app.get(f"/api/orders/{order_id}/deliverable")
    assert res.status_code == 409


# ============== 生产加固 ==============

def test_zombie_worker_cannot_overwrite_terminal_state(order_store):
    _create(order_store)
    order_store.mark_paid("ord_test1")
    order_store.claim_next("worker_a")
    order_store.mark_running("ord_test1")
    order_store.set_result("ord_test1", {"report_id": "r1"})
    # 僵尸进程后续写进度/失败不得覆写终态
    assert order_store.update_progress("ord_test1", 10, "zombie") is False
    assert order_store.set_failed("ord_test1", "zombie error") is False
    order = order_store.get("ord_test1")
    assert order["status"] == STATUS_SUCCEEDED
    assert order["progress"] == 100
    assert order["error"] is None


def test_progress_blocked_before_assignment(order_store):
    _create(order_store)  # PENDING_PAYMENT
    assert order_store.update_progress("ord_test1", 50, "x") is False


def test_stale_running_recovered_on_startup(tmp_path):
    from datetime import datetime, timedelta
    store = OrderStore(db_path=os.path.join(str(tmp_path), "o.db"))
    store.create(order_id="ord_stale", product_id="p", scenario="ecommerce", paid=True)
    store.claim_next("dead_worker")
    store.mark_running("ord_stale")
    # 心跳置为 20 分钟前
    stale_time = (datetime.now() - timedelta(minutes=20)).isoformat()
    import sqlite3
    conn = sqlite3.connect(store.db_path)
    conn.execute("UPDATE orders SET heartbeat_at = ? WHERE order_id = 'ord_stale'", (stale_time,))
    conn.commit(); conn.close()

    from app.worker import OrderWorker
    worker = OrderWorker(worker_id="recover", concurrency=1, store=store)
    recovered = worker.recover_stale_orders(timeout_minutes=10)
    assert recovered == 1
    assert store.get("ord_stale")["status"] == STATUS_QUEUED
    # 无心跳的新认领单不会被误回收
    store.claim_next("worker_b")
    worker2 = OrderWorker(worker_id="recover2", concurrency=1, store=store)
    assert worker2.recover_stale_orders(timeout_minutes=10) == 0


def test_hidden_sku_cannot_be_ordered(order_app):
    res = order_app.post("/api/orders", data={
        "product_id": "ecommerce_launch_dev",
        "user_email": "buyer@example.com",
        "payload": json.dumps({"product_name": "x", "price_point": "y",
                               "target_audience": "z", "launch_plan": "w"}),
    }, content_type="multipart/form-data")
    assert res.status_code == 400
    assert "下架" in res.get_json()["error"]


def test_orders_list_requires_email_isolation(order_app):
    _submit_order(order_app)
    # 不带 user_email → 403（数据隔离）
    res = order_app.get("/api/orders")
    assert res.status_code == 403
    # 带 email → 只能看到自己的
    res = order_app.get("/api/orders", query_string={"user_email": "buyer@example.com"})
    assert res.status_code == 200
    assert len(res.get_json()["data"]) == 1
    # 他人邮箱 → 看不到
    res = order_app.get("/api/orders", query_string={"user_email": "other@example.com"})
    assert res.status_code == 200
    assert res.get_json()["data"] == []


def test_deliverable_requires_matching_email(order_app, tmp_path):
    res = _submit_order(order_app)
    order_id = res.get_json()["data"]["order_id"]
    # 未完成 → 409 先于邮箱校验
    res = order_app.get(f"/api/orders/{order_id}/deliverable",
                        query_string={"email": "buyer@example.com"})
    assert res.status_code == 409
    # 手动置成功 + 写交付物
    from app.models.order import OrderStore
    import app.api.order as order_api
    store = order_api.get_store()
    store.claim_next("w")  # ASSIGNED
    store.mark_running(order_id)
    store.set_result(order_id, {"report_id": "r"})
    from app.services.report_export import save_deliverable
    save_deliverable(order_id, "<html>ok</html>")
    # 邮箱不匹配 → 403
    res = order_app.get(f"/api/orders/{order_id}/deliverable",
                        query_string={"email": "hacker@example.com"})
    assert res.status_code == 403
    # 匹配 → 200
    res = order_app.get(f"/api/orders/{order_id}/deliverable",
                        query_string={"email": "buyer@example.com"})
    assert res.status_code == 200


def test_dev_pay_blocked_when_not_allowed(order_app, monkeypatch):
    monkeypatch.setattr(Config, "ALLOW_DEV_PAYMENT", False)
    res = _submit_order(order_app)
    order_id = res.get_json()["data"]["order_id"]
    res = order_app.post(f"/api/orders/{order_id}/pay")
    assert res.status_code == 403
    assert "免费支付已被禁用" in res.get_json()["error"]


# ============== Creem 支付渠道 ==============

def test_creem_webhook_signature_verification(monkeypatch):
    import hashlib
    import hmac as hmac_mod
    from app.services import payment

    secret = "whsec_test_123"
    monkeypatch.setattr(Config, "CREEM_WEBHOOK_SECRET", secret)
    payload = json.dumps({
        "type": "checkout.completed",
        "object": {"id": "ch_x", "metadata": {"order_id": "ord_webhook_test"}},
    }).encode("utf-8")
    good_sig = hmac_mod.new(secret.encode(), payload, hashlib.sha256).hexdigest()

    result = payment.verify_creem_webhook(payload, good_sig)
    assert result["handled"] is True
    assert result["order_id"] == "ord_webhook_test"

    with pytest.raises(payment.PaymentError, match="签名校验失败"):
        payment.verify_creem_webhook(payload, "bad_signature")

    with pytest.raises(payment.PaymentError, match="未配置"):
        monkeypatch.setattr(Config, "CREEM_WEBHOOK_SECRET", "")
        payment.verify_creem_webhook(payload, good_sig)


def test_creem_ignores_other_events(monkeypatch):
    from app.services import payment
    monkeypatch.setattr(Config, "CREEM_WEBHOOK_SECRET", "whsec_x")
    payload = json.dumps({
        "type": "subscription.paid",
        "object": {"metadata": {"order_id": "ord_x"}},
    }).encode("utf-8")
    import hashlib, hmac as hmac_mod
    sig = hmac_mod.new(b"whsec_x", payload, hashlib.sha256).hexdigest()
    result = payment.verify_creem_webhook(payload, sig)
    assert result["handled"] is False


def test_creem_mode_without_key_falls_back(monkeypatch):
    from app.services import payment
    monkeypatch.setattr(Config, "PAYMENT_MODE", "creem")
    monkeypatch.setattr(Config, "CREEM_API_KEY", None)
    assert payment.get_payment_mode() == payment.PAYMENT_MODE_DEV


def test_creem_checkout_requires_product_id(monkeypatch):
    from app.services import payment
    monkeypatch.setattr(Config, "PAYMENT_MODE", "creem")
    monkeypatch.setattr(Config, "CREEM_API_KEY", "key_x")
    with pytest.raises(payment.PaymentError, match="creem_product_id"):
        payment.create_checkout({"order_id": "ord_y", "creem_product_id": None})


def test_product_field_creem_product_id(isolated_catalog):
    p = ProductManager.get_product("ecommerce_launch_std")
    assert p.creem_product_id is None  # 默认未配置
    p.creem_product_id = "prod_test_123"
    ProductManager.upsert_product(p)
    assert ProductManager.get_product("ecommerce_launch_std").creem_product_id == "prod_test_123"


# ============== 全场景接入 ==============

def test_all_seven_scenarios_registered():
    from app.scenarios import SCENARIOS
    expected = {
        "public_opinion", "ecommerce", "saas_pricing", "brand_crisis",
        "competitor_response", "creator_content", "listing_review",
    }
    assert set(SCENARIOS.keys()) == expected


def test_all_public_products_orderable(isolated_catalog):
    """7 个 SKU：2 个电商在售 + 5 个已激活（非 coming_soon）"""
    products = ProductManager.list_products()
    assert len(products) == 7, [p.product_id for p in products]
    for p in products:
        assert p.coming_soon is False, p.product_id
        if p.product_id != "listing_risk_review":
            assert p.kind == KIND_SIMULATION
            assert p.intake_schema.get("required"), p.product_id
            assert p.budget.get("max_agents"), p.product_id
    assert ProductManager.get_product("listing_risk_review").kind == "review"


def test_scenario_packs_have_distinct_prompts():
    from app.scenarios import get_scenario
    prompts = {
        s.name: s.ontology_system_prompt
        for s in (get_scenario(n) for n in
                  ("ecommerce", "saas_pricing", "brand_crisis",
                   "competitor_response", "creator_content"))
    }
    # 各场景本体 prompt 互不相同
    assert len(set(prompts.values())) == len(prompts)
    assert "SaaS" in prompts["saas_pricing"]
    assert "危机" in prompts["brand_crisis"]
    assert "竞品" in prompts["competitor_response"]
    assert "创作者" in prompts["creator_content"]


def test_all_simulation_scenarios_have_scheduled_events():
    from app.scenarios import SCENARIOS
    for name in ("saas_pricing", "brand_crisis", "competitor_response", "creator_content"):
        assert SCENARIOS[name].scheduled_events_enabled is True, name
    # 指标关键词各自区分
    assert "churn" in SCENARIOS["saas_pricing"].metric_keywords
    assert "outrage" in SCENARIOS["brand_crisis"].metric_keywords
    assert "switch" in SCENARIOS["competitor_response"].metric_keywords
    assert "churn" in SCENARIOS["creator_content"].metric_keywords


def test_compile_requirement_all_new_scenarios():
    cases = {
        "saas_pricing": {"product_name": "NoteForge", "pricing_change": "$12→$15",
                         "target_users": "开发者"},
        "brand_crisis": {"brand_name": "星尘科技", "incident_description": "充电仓过热"},
        "competitor_response": {"product_name": "耳机X",
                                "competitor_announcement": "AirPro2 发布"},
        "creator_content": {"product_name": "@TechDaily", "content_topic": "告别iPhone"},
    }
    for scenario, payload in cases.items():
        req = compile_requirement(scenario, payload)
        assert len(req) > 50, scenario
        for value in payload.values():
            assert str(value) in req, f"{scenario}: payload 值未进入需求文本"


def test_review_executor_panel_and_report(monkeypatch):
    """评审执行器：mock LLM 验证面板调用与报告组装"""
    from app.services import review_executor as re_mod

    calls = {"count": 0, "prompts": []}

    class FakeLLM:
        def chat(self, messages, **kwargs):
            calls["count"] += 1
            calls["prompts"].append(messages[0]["content"])
            if calls["count"] <= len(re_mod.REVIEW_PANEL):
                return json.dumps({
                    "scores": {"overall": 7, "appeal": 7, "trust": 6},
                    "risks": [{"type": "compliance", "severity": "high",
                               "quote": "medical grade", "issue": "未获FDA认证",
                               "suggestion": "改为 clinically tested"}],
                    "highlights": ["clear specs"],
                    "verdict": "appealing but risky claims",
                })
            return "## 综合报告\n风险可控。"

    monkeypatch.setattr(
        re_mod, "LLMClient", lambda timeout=None: FakeLLM()
    )
    outcome = re_mod.run_review(
        requirement="listing review",
        payload={"listing_title": "StarDust X", "listing_description": "medical grade noise cancelling"},
        language="en",
    )
    # 面板 5 人 + 1 次综合
    assert calls["count"] == len(re_mod.REVIEW_PANEL) + 1
    assert outcome["overall_score"] == 7.0
    assert len(outcome["panel_reviews"]) == len(re_mod.REVIEW_PANEL)
    assert "综合报告" in outcome["report_markdown"]
    # 评审团包含合规/平台审核视角
    assert any("compliance" in p for p in calls["prompts"])
    assert any("policy" in p.lower() for p in calls["prompts"])


# ============== 邮件通知服务 ==============

def test_email_skips_without_key(monkeypatch):
    from app.services import email_service
    monkeypatch.setattr(Config, "RESEND_API_KEY", "")
    result = email_service.send_order_completed(
        order_id="ord_x", user_email="test@test.com", title="测试",
        deliverable_url="/api/orders/ord_x/deliverable",
    )
    assert result is False


def test_email_sends_with_mock(monkeypatch):
    from app.services import email_service

    sent = {}
    class FakeResponse:
        def raise_for_status(self): pass
    monkeypatch.setattr(Config, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr("httpx.post", lambda url, **kw: sent.update(kw) or FakeResponse())

    result = email_service.send_order_completed(
        order_id="ord_mail_test", user_email="buyer@test.com",
        title="推演报告", deliverable_url="https://y.com/dl",
        language="zh",
    )
    assert result is True
    payload = sent.get("json", {})
    assert payload.get("to") == ["buyer@test.com"]
    assert "推演完成" in payload.get("subject", "")
    assert "y.com/dl" in payload.get("html", "")


def test_email_en_template(monkeypatch):
    from app.services import email_service
    sent = {}
    class FakeResponse:
        def raise_for_status(self): pass
    monkeypatch.setattr(Config, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr("httpx.post", lambda url, **kw: sent.update(kw) or FakeResponse())

    email_service.send_order_completed(
        order_id="ord_en", user_email="x@x.com", title="Test",
        deliverable_url="https://y.com/dl", language="en",
    )
    payload = sent.get("json", {})
    assert "Rehearsal Complete" in payload.get("subject", "")
    assert "not guarantees" in payload.get("html", "").lower() or "simulated" in payload.get("html", "").lower()
