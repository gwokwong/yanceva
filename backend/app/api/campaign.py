"""Campaign（对比预演）API。

一个 Campaign 基于一次已准备完成的基线模拟，克隆出多个变体模拟
（改价格、换 KOL 组合、调整上市节奏），串行运行后对比市场指标。
变体克隆不调用 LLM（只改写配置 JSON），对比成本主要是模拟本身。
"""

import json
import os
import shutil
import threading
import time
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional

from flask import request, jsonify

from . import campaign_bp
from ..config import Config
from ..models.campaign import (
    CAMPAIGN_COMPLETED,
    CAMPAIGN_CREATED,
    CAMPAIGN_FAILED,
    CAMPAIGN_RUNNING,
    Campaign,
    CampaignManager,
    CampaignVariant,
)
from ..models.task import TaskManager, TaskStatus
from ..services.market_metrics_service import MarketMetricsService
from ..services.simulation_manager import SimulationManager, SimulationStatus
from ..services.simulation_runner import SimulationRunner, RunnerStatus
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from ..utils.locale import t, get_locale, set_locale

logger = get_logger('mirofish.api.campaign')

# 单个变体模拟的最长等待时间（秒）
VARIANT_RUN_TIMEOUT_SECONDS = 2 * 60 * 60
# 运行状态轮询间隔（秒）
RUN_POLL_INTERVAL_SECONDS = 10

# 不应随变体克隆的运行时产物
_RUN_ARTIFACTS = (
    "run_state.json",
    "market_metrics.json",
    "metrics_state.json",
    "simulation.log",
    "env_status.json",
    "ipc_commands",
    "ipc_responses",
)

TERMINAL_RUNNER_STATUSES = {
    RunnerStatus.COMPLETED,
    RunnerStatus.STOPPED,
    RunnerStatus.FAILED,
}


# ============== 变体克隆与配置改写 ==============

def _match_agent_id(poster_type: str, agent_configs: List[Dict[str, Any]]) -> Optional[int]:
    """按实体类型为帖子/事件找一个发布者 Agent（类型别名宽松匹配）。"""
    poster = (poster_type or "").lower()
    direct = [
        cfg for cfg in agent_configs
        if (cfg.get("entity_type") or "").lower() == poster
    ]
    if direct:
        return direct[0]["agent_id"]
    partial = [
        cfg for cfg in agent_configs
        if poster and poster in (cfg.get("entity_type") or "").lower()
    ]
    if partial:
        return partial[0]["agent_id"]
    return None


def apply_variant_overrides(
    config: Dict[str, Any],
    overrides: Dict[str, Any],
) -> Dict[str, Any]:
    """把变体的 overrides 应用到克隆的 simulation_config 上（就地修改并返回）。

    支持的 overrides：
    - content_replacements: {"旧": "新"} —— 对所有事件帖内容与模拟需求做文本替换
      （典型用法：{"249": "199"} 改价格）
    - initial_posts / scheduled_events: 整表替换（poster_type 自动匹配 Agent）
    - kol_agent_ids: [agent_id] —— 提升这些 Agent 的影响力与活跃度
    - metrics_keywords: {"price": [...]} —— 追加指标关键词
    - product_name: "..." —— 问卷探针中的产品名
    - requirement_appendix: "..." —— 追加到模拟需求
    """
    replacements = overrides.get("content_replacements") or {}

    def _replace(text: str) -> str:
        for old, new in replacements.items():
            if isinstance(old, str) and old:
                text = text.replace(old, new)
        return text

    agent_configs = config.get("agent_configs") or []

    # 1. 模拟需求
    if overrides.get("requirement_appendix"):
        config["simulation_requirement"] = (
            f"{config.get('simulation_requirement', '')}\n{overrides['requirement_appendix']}"
        )
    if replacements:
        config["simulation_requirement"] = _replace(config.get("simulation_requirement", ""))

    event_config = config.get("event_config") or {}

    # 2. 初始帖子整表替换
    if overrides.get("initial_posts") is not None:
        posts = []
        for post in overrides["initial_posts"]:
            post = dict(post)
            post["content"] = _replace(post.get("content", ""))
            if post.get("poster_agent_id") is None:
                post["poster_agent_id"] = _match_agent_id(
                    post.get("poster_type", ""), agent_configs
                )
            posts.append(post)
        event_config["initial_posts"] = posts
    elif replacements:
        for post in event_config.get("initial_posts") or []:
            post["content"] = _replace(post.get("content", ""))

    # 3. 定时事件整表替换
    if overrides.get("scheduled_events") is not None:
        events = []
        for event in overrides["scheduled_events"]:
            event = dict(event)
            event["content"] = _replace(event.get("content", ""))
            if event.get("poster_agent_id") is None:
                event["poster_agent_id"] = _match_agent_id(
                    event.get("poster_type", ""), agent_configs
                )
            try:
                event["trigger_round"] = int(event.get("trigger_round", 0) or 0)
            except (TypeError, ValueError):
                event["trigger_round"] = 0
            events.append(event)
        event_config["scheduled_events"] = events
    elif replacements:
        for event in event_config.get("scheduled_events") or []:
            event["content"] = _replace(event.get("content", ""))

    config["event_config"] = event_config

    # 4. KOL 组合调整
    kol_ids = set(overrides.get("kol_agent_ids") or [])
    if kol_ids:
        for cfg in agent_configs:
            if cfg.get("agent_id") in kol_ids:
                cfg["influence_weight"] = round(cfg.get("influence_weight", 1.0) * 1.5, 2)
                cfg["activity_level"] = min(1.0, cfg.get("activity_level", 0.5) + 0.1)
                cfg["posts_per_hour"] = round(cfg.get("posts_per_hour", 0.5) * 1.3, 2)

    # 5. 指标关键词追加
    if overrides.get("metrics_keywords"):
        merged = dict(config.get("metrics_keywords") or {})
        for key, words in overrides["metrics_keywords"].items():
            merged[key] = list(words) + merged.get(key, [])
        config["metrics_keywords"] = merged

    # 6. 产品名（问卷探针用）
    if overrides.get("product_name"):
        config["product_name"] = overrides["product_name"]
    elif replacements:
        if config.get("product_name"):
            config["product_name"] = _replace(config["product_name"])

    return config


def _clone_base_simulation(base_simulation_id: str, variant_simulation_id: str) -> None:
    """复制基线模拟目录（人设/配置），剔除运行时产物。"""

    base_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, base_simulation_id)
    target_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, variant_simulation_id)

    if not os.path.isdir(base_dir):
        raise ValueError(f"基线模拟目录不存在: {base_simulation_id}")

    if os.path.exists(target_dir):
        shutil.rmtree(target_dir)
    shutil.copytree(
        base_dir,
        target_dir,
        ignore=shutil.ignore_patterns(
            *[artifact.rstrip("/") + "*" for artifact in _RUN_ARTIFACTS]
        ),
    )


def _reset_cloned_state(variant_simulation_id: str, scenario: str) -> None:
    """重置克隆目录中的 state.json，并同步 SimulationManager 缓存。"""

    manager = SimulationManager()
    state = manager.create_simulation(
        project_id="",  # 稍后从克隆的 state.json 恢复
        graph_id="",
        scenario=scenario,
    )
    # create_simulation 生成了自己的临时 id，这里改成变体 id 并恢复字段
    temp_simulation_id = state.simulation_id
    state.simulation_id = variant_simulation_id
    state_file = os.path.join(
        Config.OASIS_SIMULATION_DATA_DIR, variant_simulation_id, "state.json"
    )
    if os.path.exists(state_file):
        with open(state_file, 'r', encoding='utf-8') as f:
            cloned = json.load(f) or {}
    else:
        cloned = {}
    state.project_id = cloned.get("project_id", "")
    state.graph_id = cloned.get("graph_id", "")
    state.enable_twitter = cloned.get("enable_twitter", True)
    state.enable_reddit = cloned.get("enable_reddit", True)
    state.entities_count = cloned.get("entities_count", 0)
    state.profiles_count = cloned.get("profiles_count", 0)
    state.entity_types = cloned.get("entity_types", [])
    state.profiles_generated = cloned.get("profiles_generated", False)
    state.config_generated = cloned.get("config_generated", False)
    state.status = SimulationStatus.READY
    manager._save_simulation_state(state)

    # 清理临时 id 的缓存与目录
    manager._simulations.pop(temp_simulation_id, None)
    shutil.rmtree(
        os.path.join(Config.OASIS_SIMULATION_DATA_DIR, temp_simulation_id),
        ignore_errors=True,
    )


def _create_variant_simulation(
    base_simulation_id: str,
    label: str,
    overrides: Dict[str, Any],
    scenario: str,
) -> CampaignVariant:
    """克隆基线模拟并应用 overrides，生成一个变体。"""

    import uuid as _uuid

    variant_simulation_id = f"sim_{_uuid.uuid4().hex[:12]}"

    _clone_base_simulation(base_simulation_id, variant_simulation_id)

    config_path = os.path.join(
        Config.OASIS_SIMULATION_DATA_DIR, variant_simulation_id, "simulation_config.json"
    )
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    config["simulation_id"] = variant_simulation_id
    config = apply_variant_overrides(config, overrides)

    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    _reset_cloned_state(variant_simulation_id, scenario)

    variant_id = f"var_{_uuid.uuid4().hex[:8]}"
    return CampaignVariant(
        variant_id=variant_id,
        label=label,
        simulation_id=variant_simulation_id,
        overrides=overrides,
    )


# ============== 对比聚合 ==============

def _variant_metrics_summary(simulation_id: str) -> Dict[str, Any]:
    service = MarketMetricsService()
    metrics = service.compute_metrics(simulation_id)
    totals = metrics.get("totals") or {}

    sentiments = [
        s.get("sentiment_avg") for s in metrics.get("series", [])
        if isinstance(s.get("sentiment_avg"), (int, float))
    ]
    intents = [
        s.get("purchase_intent_avg") for s in metrics.get("series", [])
        if isinstance(s.get("purchase_intent_avg"), (int, float))
    ]

    return {
        "simulation_id": simulation_id,
        "rounds": totals.get("rounds", 0),
        "posts": totals.get("posts", 0),
        "comments": totals.get("comments", 0),
        "keyword_hits": totals.get("keyword_hits", {}),
        "sentiment_avg": (
            round(sum(sentiments) / len(sentiments), 3) if sentiments else None
        ),
        "purchase_intent_avg": (
            round(sum(intents) / len(intents), 3) if intents else None
        ),
        "survey_count": totals.get("survey_count", 0),
        "series": metrics.get("series", []),
    }


def build_comparison(campaign: Campaign) -> Dict[str, Any]:
    """聚合所有变体（含基线）的市场指标，输出对比表与 Δ 值。"""

    summaries: List[Dict[str, Any]] = []

    # 基线（若已完成准备）
    manager = SimulationManager()
    base_state = manager.get_simulation(campaign.base_simulation_id)
    if base_state and base_state.config_generated:
        try:
            baseline = _variant_metrics_summary(campaign.base_simulation_id)
            baseline["variant_id"] = "baseline"
            baseline["label"] = "基线"
            summaries.append(baseline)
        except Exception as e:
            logger.warning(f"基线指标聚合失败: {e}")

    for variant in campaign.variants:
        try:
            summary = _variant_metrics_summary(variant.simulation_id)
            summary["variant_id"] = variant.variant_id
            summary["label"] = variant.label
            summaries.append(summary)
        except Exception as e:
            logger.warning(f"变体 {variant.variant_id} 指标聚合失败: {e}")

    if not summaries:
        return {"campaign_id": campaign.campaign_id, "summaries": [], "delta": {}}

    # 以第一个条目为参照计算 Δ
    reference = summaries[0]
    delta: List[Dict[str, Any]] = []
    for summary in summaries[1:]:
        delta.append({
            "variant_id": summary["variant_id"],
            "label": summary["label"],
            "posts_delta": summary["posts"] - reference["posts"],
            "comments_delta": summary["comments"] - reference["comments"],
            "sentiment_delta": (
                round(summary["sentiment_avg"] - reference["sentiment_avg"], 3)
                if summary["sentiment_avg"] is not None and reference["sentiment_avg"] is not None
                else None
            ),
            "purchase_intent_delta": (
                round(summary["purchase_intent_avg"] - reference["purchase_intent_avg"], 3)
                if summary["purchase_intent_avg"] is not None and reference["purchase_intent_avg"] is not None
                else None
            ),
        })

    return {
        "campaign_id": campaign.campaign_id,
        "summaries": summaries,
        "delta": {"reference": reference.get("label"), "rows": delta},
        "generated_at": datetime.now().isoformat(),
    }


# ============== 串行运行 worker ==============

def _run_campaign_worker(campaign_id: str, task_id: str, locale: str) -> None:
    set_locale(locale)
    task_manager = TaskManager()

    try:
        campaign = CampaignManager.get_campaign(campaign_id)
        if campaign is None:
            task_manager.fail_task(task_id, "Campaign 不存在")
            return

        campaign.status = CAMPAIGN_RUNNING
        CampaignManager.save_campaign(campaign)

        total = len(campaign.variants)
        for index, variant in enumerate(campaign.variants):
            task_manager.update_task(
                task_id,
                progress=int(index / max(total, 1) * 100),
                message=f"运行变体 [{index + 1}/{total}]: {variant.label}",
            )

            state = SimulationManager().get_simulation(variant.simulation_id)
            if state is None or not state.config_generated:
                campaign.run_status[variant.simulation_id] = "failed"
                campaign.error = f"变体 {variant.label} 的模拟配置缺失"
                CampaignManager.save_campaign(campaign)
                continue

            try:
                SimulationRunner.start_simulation(
                    simulation_id=variant.simulation_id,
                    platform="parallel",
                    max_rounds=campaign.max_rounds,  # 成本护栏
                    enable_graph_memory_update=False,  # 变体不回写图谱，避免污染基线
                )
            except Exception as e:
                campaign.run_status[variant.simulation_id] = "failed"
                campaign.error = f"变体 {variant.label} 启动失败: {e}"
                CampaignManager.save_campaign(campaign)
                continue

            campaign.run_status[variant.simulation_id] = "running"
            CampaignManager.save_campaign(campaign)

            # 等待到终态
            deadline = time.time() + VARIANT_RUN_TIMEOUT_SECONDS
            final_status = "failed"
            while time.time() < deadline:
                time.sleep(RUN_POLL_INTERVAL_SECONDS)
                run_state = SimulationRunner.get_run_state(variant.simulation_id)
                status = getattr(run_state, "runner_status", None)
                if status in TERMINAL_RUNNER_STATUSES:
                    final_status = status.value if hasattr(status, "value") else str(status)
                    break

            campaign.run_status[variant.simulation_id] = final_status
            CampaignManager.save_campaign(campaign)

            # 计算市场指标（含 LLM 分类）
            try:
                MarketMetricsService().compute_metrics(
                    variant.simulation_id, classify=True
                )
            except Exception as e:
                logger.warning(f"变体 {variant.label} 指标计算失败: {e}")

        campaign.status = CAMPAIGN_COMPLETED
        CampaignManager.save_campaign(campaign)
        task_manager.complete_task(
            task_id,
            result={"campaign_id": campaign_id, "status": campaign.status},
        )

    except Exception as e:
        logger.error(f"Campaign 运行失败: {e}\n{traceback.format_exc()}")
        campaign = CampaignManager.get_campaign(campaign_id)
        if campaign is not None:
            campaign.status = CAMPAIGN_FAILED
            campaign.error = str(e)
            CampaignManager.save_campaign(campaign)
        task_manager.fail_task(task_id, str(e))


# ============== 路由 ==============

@campaign_bp.route('/create', methods=['POST'])
def create_campaign():
    """
    创建对比预演计划（克隆变体，不调用 LLM）

    请求（JSON）：
        {
            "name": "价格 A/B 预演",
            "base_simulation_id": "sim_xxx",   // 必填，已准备完成的基线模拟
            "variants": [
                {
                    "label": "定价199",
                    "overrides": {"content_replacements": {"249": "199"}}
                },
                {
                    "label": "换KOL组合",
                    "overrides": {"kol_agent_ids": [3, 7]}
                }
            ]
        }
    """
    try:
        data = request.get_json() or {}
        base_simulation_id = data.get('base_simulation_id')
        variants_input = data.get('variants') or []

        if not base_simulation_id:
            return jsonify({"success": False, "error": "缺少 base_simulation_id"}), 400
        if not variants_input or not isinstance(variants_input, list):
            return jsonify({"success": False, "error": "至少需要一个变体"}), 400
        if len(variants_input) > 5:  # 资源保护
            return jsonify({"success": False, "error": "变体数量最多 5 个"}), 400

        manager = SimulationManager()
        base_state = manager.get_simulation(base_simulation_id)
        if base_state is None:
            return jsonify({"success": False, "error": "基线模拟不存在"}), 404
        if not base_state.config_generated:
            return jsonify({
                "success": False,
                "error": "基线模拟尚未完成准备（prepare），无法克隆"
            }), 400

        scenario = base_state.scenario
        variants: List[CampaignVariant] = []
        for i, item in enumerate(variants_input):
            label = (item.get('label') or f"变体{i + 1}").strip()[:50]
            overrides = item.get('overrides') or {}
            variants.append(
                _create_variant_simulation(
                    base_simulation_id, label, overrides, scenario
                )
            )

        max_rounds = data.get('max_rounds')
        if max_rounds is not None:
            try:
                max_rounds = max(6, min(int(max_rounds), 200))
            except (TypeError, ValueError):
                max_rounds = None

        campaign = CampaignManager.create_campaign(
            name=(data.get('name') or '对比预演').strip()[:100],
            base_simulation_id=base_simulation_id,
            scenario=scenario,
            variants=variants,
            max_rounds=max_rounds,
        )
        return jsonify({"success": True, "data": campaign.to_dict()})

    except Exception as e:
        logger.error(f"创建 Campaign 失败: {e}\n{traceback.format_exc()}")
        return jsonify({"success": False, "error": str(e)}), 500


@campaign_bp.route('/<campaign_id>/run', methods=['POST'])
def run_campaign(campaign_id: str):
    """串行运行全部变体模拟（异步任务）。"""
    try:
        campaign = CampaignManager.get_campaign(campaign_id)
        if campaign is None:
            return jsonify({"success": False, "error": "Campaign 不存在"}), 404
        if campaign.status == CAMPAIGN_RUNNING:
            return jsonify({"success": False, "error": "Campaign 正在运行中"}), 409

        task_manager = TaskManager()
        task_id = task_manager.create_task(
            task_type="campaign_run",
            metadata={"campaign_id": campaign_id},
        )
        campaign.run_task_id = task_id
        campaign.run_status = {}
        campaign.status = CAMPAIGN_CREATED
        CampaignManager.save_campaign(campaign)

        current_locale = get_locale()
        thread = threading.Thread(
            target=_run_campaign_worker,
            args=(campaign_id, task_id, current_locale),
            daemon=True,
        )
        thread.start()

        return jsonify({
            "success": True,
            "data": {"campaign_id": campaign_id, "task_id": task_id}
        })

    except Exception as e:
        logger.error(f"启动 Campaign 失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@campaign_bp.route('/<campaign_id>', methods=['GET'])
def get_campaign(campaign_id: str):
    """查询 Campaign 详情与变体运行状态。"""
    campaign = CampaignManager.get_campaign(campaign_id)
    if campaign is None:
        return jsonify({"success": False, "error": "Campaign 不存在"}), 404

    data = campaign.to_dict()
    # 附带变体模拟的实时状态
    manager = SimulationManager()
    live = {}
    for variant in campaign.variants:
        state = manager.get_simulation(variant.simulation_id)
        live[variant.simulation_id] = {
            "status": state.status.value if state else "unknown",
            "current_round": getattr(state, "current_round", 0) if state else 0,
            "run_status": campaign.run_status.get(variant.simulation_id, ""),
        }
    data["variants_live"] = live
    return jsonify({"success": True, "data": data})


@campaign_bp.route('/list', methods=['GET'])
def list_campaigns():
    campaigns = CampaignManager.list_campaigns()
    return jsonify({
        "success": True,
        "data": [c.to_dict() for c in campaigns]
    })


@campaign_bp.route('/<campaign_id>/comparison', methods=['GET'])
def get_campaign_comparison(campaign_id: str):
    """获取全部变体的市场指标对比（规则聚合，零 LLM）。"""
    campaign = CampaignManager.get_campaign(campaign_id)
    if campaign is None:
        return jsonify({"success": False, "error": "Campaign 不存在"}), 404
    try:
        comparison = build_comparison(campaign)
        return jsonify({"success": True, "data": comparison})
    except Exception as e:
        logger.error(f"对比聚合失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


COMPARISON_SYSTEM_PROMPT = (
    "你是电商市场分析专家。基于多组预演变体的市场指标与摘要，撰写一份简明的"
    "「对比预演报告」（Markdown，800-1500字）：对比各变体在声量、情绪、购买意愿、"
    "价格讨论热度上的差异，给出明确的方案建议（哪个变体更优、为什么），"
    "并用表格呈现关键指标对比。只输出报告内容。"
)


@campaign_bp.route('/<campaign_id>/report', methods=['POST'])
def generate_campaign_report(campaign_id: str):
    """基于指标对比生成 LLM 对比报告（轻量：单次 LLM 调用）。"""
    try:
        campaign = CampaignManager.get_campaign(campaign_id)
        if campaign is None:
            return jsonify({"success": False, "error": "Campaign 不存在"}), 404

        comparison = build_comparison(campaign)
        if not comparison.get("summaries"):
            return jsonify({"success": False, "error": "暂无可对比的指标数据"}), 400

        # 每个变体的详细摘要（截断，控制上下文）
        service = MarketMetricsService()
        detail_parts = []
        for summary in comparison["summaries"]:
            sim_id = summary["simulation_id"]
            text = service.get_report_summary(sim_id)
            detail_parts.append(f"### {summary['label']} ({sim_id})\n{text[:4000]}")

        llm = LLMClient(timeout=300.0)
        report_md = llm.chat(
            messages=[
                {"role": "system", "content": COMPARISON_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"预演计划：{campaign.name}\n"
                        f"场景：{campaign.scenario}\n\n"
                        "指标对比表（Δ 为相对基线的变化）：\n"
                        f"{json.dumps(comparison.get('delta', {}), ensure_ascii=False, indent=2)}\n\n"
                        "各变体详细指标：\n" + "\n\n".join(detail_parts)
                    ),
                },
            ],
            temperature=0.4,
        )

        campaign.comparison_report = {
            "markdown": report_md,
            "generated_at": datetime.now().isoformat(),
        }
        CampaignManager.save_campaign(campaign)

        return jsonify({"success": True, "data": campaign.comparison_report})

    except Exception as e:
        logger.error(f"对比报告生成失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@campaign_bp.route('/<campaign_id>', methods=['DELETE'])
def delete_campaign(campaign_id: str):
    """删除 Campaign（变体模拟目录保留，可单独清理）。"""
    deleted = CampaignManager.delete_campaign(campaign_id)
    if not deleted:
        return jsonify({"success": False, "error": "Campaign 不存在"}), 404
    return jsonify({"success": True, "data": {"campaign_id": campaign_id}})
