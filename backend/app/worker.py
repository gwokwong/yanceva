"""平台 Worker：从订单队列认领任务并驱动完整预演链路。

链路（复用现有服务，与前端流程一致）：
  编译需求 → 建项目 → 本体生成 → 图谱构建(Graphiti/Neo4j) →
  模拟准备(场景过滤/Agent上限) → 双平台模拟(定时事件) →
  市场指标(LLM分类) → 报告(ReACT) → 交付物 HTML → 结果入库

运行：cd backend && uv run python -m app.worker            # 常驻轮询
      uv run python -m app.worker --once                    # 处理一单退出（验收用）
      uv run python -m app.worker --concurrency 2           # 并发执行

Worker 可部署在任意"性能不太行"的机器上——本地只有编排开销，
重活全在 DeepSeek 云端 API；Embedding 走内网 Ollama。
"""

from __future__ import annotations

import argparse
import os
import shutil
import threading
import time
import traceback
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from .config import Config
from .models.order import (
    OrderStore,
    STATUS_CANCELLED,
    STATUS_FAILED,
    STATUS_SUCCEEDED,
)
from .models.product import KIND_REVIEW, KIND_SIMULATION, ProductManager
from .services.simulation_manager import SimulationManager, SimulationStatus
from .services.simulation_runner import SimulationRunner, RunnerStatus
from .services.market_metrics_service import MarketMetricsService
from .scenarios.listing_review import REVIEW_PANEL
from .services.review_executor import run_review
from .services.report_agent import ReportAgent
from .services.report_export import build_deliverable_html, save_deliverable
from .services import email_service
from .services.ontology_generator import OntologyGenerator
from .services.graph_builder import GraphBuilderService
from .services.text_processor import TextProcessor
from .services.zep_graph_memory_updater import ZepGraphMemoryManager
from .models.project import ProjectManager, ProjectStatus
from .models.task import TaskManager
from .utils.file_parser import FileParser
from .utils.logger import setup_logger, get_logger
from .utils.locale import set_locale

logger = get_logger('mirofish.worker')

HEARTBEAT_INTERVAL_SECONDS = 30
SIM_POLL_INTERVAL_SECONDS = 10


def compile_requirement(scenario: str, payload: Dict[str, Any]) -> str:
    """把提交表单编译成模拟需求文本（每个场景一个编译器）。"""

    if scenario == "saas_pricing":
        parts = ["【SaaS 定价/改版沙盘】",
                 f"产品：{payload.get('product_name', '')}。"]
        if payload.get('pricing_change'):
            parts.append(f"定价/改版方案：{payload['pricing_change']}。")
        if payload.get('target_users'):
            parts.append(f"目标用户：{payload['target_users']}。")
        if payload.get('competitors'):
            parts.append(f"竞品与替代品：{payload['competitors']}。")
        if payload.get('concerns'):
            parts.append(f"重点推演的风险（客户特别关注）：{payload['concerns']}。")
        parts.append("请预演该定价调整/改版发布后的用户反应：社区舆论、流失风险、"
                     "定价接受度、竞品截流与应对。")
        return "\n".join(parts)

    if scenario == "brand_crisis":
        parts = ["【品牌危机回应预演】",
                 f"品牌：{payload.get('brand_name', '')}。"]
        if payload.get('incident_description'):
            parts.append(f"危机事件：{payload['incident_description']}。")
        if payload.get('planned_response'):
            parts.append(f"品牌准备的回应话术：{payload['planned_response']}")
        if payload.get('audience'):
            parts.append(f"受众与传播圈层：{payload['audience']}。")
        if payload.get('concerns'):
            parts.append(f"重点推演的风险（客户特别关注）：{payload['concerns']}。")
        parts.append("请预演危机事件的传播路径、用户情绪演化、回应话术效果与二次引爆点。")
        return "\n".join(parts)

    if scenario == "competitor_response":
        parts = ["【竞品发布应对沙盘】",
                 f"我方产品：{payload.get('product_name', '')}。"]
        if payload.get('competitor_announcement'):
            parts.append(f"竞品发布动作：{payload['competitor_announcement']}。")
        if payload.get('our_strengths'):
            parts.append(f"我方优势与应对资源：{payload['our_strengths']}。")
        if payload.get('target_audience'):
            parts.append(f"目标用户：{payload['target_audience']}。")
        if payload.get('concerns'):
            parts.append(f"重点推演的风险（客户特别关注）：{payload['concerns']}。")
        parts.append("请预演竞品发布冲击下的市场反应与用户流失风险，并测试我方应对动作的效果。")
        return "\n".join(parts)

    if scenario == "creator_content":
        parts = ["【创作者内容风险预演】",
                 f"创作者/频道：{payload.get('product_name', '')}。"]
        if payload.get('content_topic'):
            parts.append(f"本期内容主题：{payload['content_topic']}。")
        if payload.get('content_outline'):
            parts.append(f"内容大纲/关键表达：{payload['content_outline']}")
        if payload.get('audience'):
            parts.append(f"受众画像：{payload['audience']}。")
        if payload.get('concerns'):
            parts.append(f"重点推演的风险（客户特别关注）：{payload['concerns']}。")
        parts.append("请预演该内容发布后的受众反应：争议点、掉粉风险、品牌方敏感点与替代表达建议。")
        return "\n".join(parts)

    if scenario == "ecommerce":
        parts = [
            f"【电商新品上市预演】",
            f"产品：{payload.get('product_name', '')}，定价 {payload.get('price_point', '')}。",
        ]
        if payload.get('key_features'):
            parts.append(f"核心卖点：{payload['key_features']}。")
        if payload.get('target_audience'):
            parts.append(f"目标人群：{payload['target_audience']}。")
        if payload.get('competitors'):
            parts.append(f"主要竞品：{payload['competitors']}。")
        parts.append(f"上市计划：{payload.get('launch_plan', '')}")
        if payload.get('concerns'):
            parts.append(f"重点推演的风险（客户特别关注）：{payload['concerns']}。")
        parts.append("请预演该新品上市的市场反应：声量与情绪走势、购买意愿与价格接受度、"
                     "KOL投放效果、竞品动态与应对。")
        return "\n".join(parts)
    # 未知场景：直接拼接所有非空字段
    return "\n".join(f"{k}: {v}" for k, v in payload.items() if v)


class SimulationCancelled(Exception):
    """订单被用户取消，由执行流程内部抛出以中断链路。"""


class OrderWorker:
    def __init__(self, worker_id: str, concurrency: int = 1, poll_interval: int = 5,
                 store: Optional[OrderStore] = None):
        self.worker_id = worker_id
        self.concurrency = max(1, concurrency)
        self.poll_interval = max(1, poll_interval)
        self.store = store or OrderStore()
        self._threads: list = []
        self._shutdown = threading.Event()

    # ── 主循环 ────────────────────────────────────────────────

    def recover_stale_orders(self, timeout_minutes: int = 10) -> int:
        """启动时回收：心跳超时的执行中订单重回队列（worker 崩溃恢复）。"""
        stale = self.store.find_stale_running(timeout_minutes)
        recovered = 0
        for order in stale:
            # 心跳从未更新过的新单（刚认领）不回收
            if not order.get("heartbeat_at"):
                continue
            if self.store.requeue(order["order_id"]):
                recovered += 1
                logger.warning(f"回收陈旧订单 {order['order_id']}（worker 失联）")
            else:
                # 超过重试上限：标记失败并通知
                self.store.set_failed(
                    order["order_id"], "多次执行失败（超过重试上限），已停止自动重试"
                )
                logger.warning(f"订单 {order['order_id']} 超过重试上限，标记失败")
        return recovered

    def run_forever(self) -> None:
        recovered = self.recover_stale_orders()
        logger.info(f"Worker {self.worker_id} 启动（并发={self.concurrency}，"
                    f"轮询={self.poll_interval}s，回收={recovered}）")
        while not self._shutdown.is_set():
            capacity = self.concurrency - self._active_count()
            if capacity <= 0:
                time.sleep(self.poll_interval)
                continue
            claimed = 0
            for _ in range(capacity):
                order = self.store.claim_next(self.worker_id)
                if order is None:
                    break
                product = ProductManager.get_product(order["product_id"])
                if product is None or product.kind not in (KIND_SIMULATION, KIND_REVIEW):
                    self.store.set_failed(order["order_id"], f"商品不可执行: {order['product_id']}")
                    continue
                thread = threading.Thread(
                    target=self._run_order_safely,
                    args=(order, product),
                    daemon=True,
                )
                self._threads.append(thread)
                thread.start()
                claimed += 1
            if claimed == 0:
                time.sleep(self.poll_interval)

    def run_once(self) -> Optional[Dict[str, Any]]:
        """处理一单（阻塞到完成），端到端验收用。"""
        self.recover_stale_orders()
        order = self.store.claim_next(self.worker_id)
        if order is None:
            logger.info("队列中无待处理订单")
            return None
        product = ProductManager.get_product(order["product_id"])
        if product is None or product.kind not in (KIND_SIMULATION, KIND_REVIEW):
            self.store.set_failed(order["order_id"], f"商品不可执行: {order['product_id']}")
            return None
        self._run_order_safely(order, product)
        return self.store.get(order["order_id"])

    def stop(self) -> None:
        self._shutdown.set()

    def _active_count(self) -> int:
        self._threads = [t for t in self._threads if t.is_alive()]
        return len(self._threads)

    # ── 执行 ──────────────────────────────────────────────────

    def _run_order_safely(self, order: Dict[str, Any], product) -> None:
        order_id = order["order_id"]
        # 报告语言跟随客户提交时的选择（海外客户默认英文更合适）
        language = (order.get("payload") or {}).get("language", "zh")
        set_locale(language)
        try:
            if product.kind == KIND_REVIEW:
                self._execute_review_order(order, product, language)
            else:
                self._execute_order(order, product, language)
        except SimulationCancelled:
            self.store.mark_cancelled(order_id)
            logger.info(f"订单 {order_id} 已按用户请求取消")
        except Exception as e:
            logger.error(f"订单 {order_id} 执行失败: {e}\n{traceback.format_exc()}")
            self.store.set_failed(order_id, str(e))

    def _check_cancelled(self, order_id: str) -> None:
        if self.store.is_cancel_requested(order_id):
            raise SimulationCancelled()

    def _progress(self, order_id: str, progress: int, stage: str, detail: Any = None) -> None:
        self.store.update_progress(order_id, progress, stage, detail)
        self.store.heartbeat(order_id)

    def _execute_review_order(self, order: Dict[str, Any], product, language: str = "zh") -> None:
        """评审单链路：多角色评审 → 综合报告 → 交付物。无模拟/图谱。"""
        order_id = order["order_id"]
        payload = order.get("payload") or {}
        requirement = compile_requirement(product.scenario, payload)
        heartbeat_stop = threading.Event()

        def heartbeat_loop():
            while not heartbeat_stop.wait(HEARTBEAT_INTERVAL_SECONDS):
                try:
                    self.store.heartbeat(order_id)
                except Exception:
                    pass

        deadline = time.time() + max(300, product.sla_minutes * 60)
        self.store.mark_running(order_id)
        threading.Thread(target=heartbeat_loop, daemon=True).start()
        logger.info(f"开始执行评审单 {order_id}（{product.name}）")

        try:
            self._check_cancelled(order_id)

            # 上传的种子资料作为评审上下文（产品说明书/规格等）
            extra_context = ""
            for file_info in order.get("files") or []:
                path = file_info.get("path")
                if path and os.path.exists(path):
                    try:
                        text = FileParser.extract_text(path)
                        extra_context += f"\n--- {file_info.get('original_name', '')} ---\n{text}"
                    except Exception as e:
                        logger.warning(f"评审资料解析失败 {path}: {e}")

            def progress(msg, fraction):
                self._progress(order_id, 10 + int(fraction * 60), "review", msg)
                if time.time() > deadline:
                    raise RuntimeError(f"超过交付时限（SLA {product.sla_minutes} 分钟）")

            outcome = run_review(
                requirement=requirement,
                payload=payload,
                language=language,
                progress_callback=progress,
                extra_context=extra_context,
            )
            self._check_cancelled(order_id)
            self._progress(order_id, 75, "review", "评审完成，生成综合报告")

            overall = outcome.get("overall_score")
            score_line = f"**综合评分：{overall}/10**\n\n" if overall is not None else ""
            report_md = (
                f"# {product.deliverable_name}\n\n"
                f"{score_line}"
                f"{outcome.get('report_markdown', '')}"
            )
            self._progress(order_id, 90, "report", "审查报告生成完成")

            deliverable = build_deliverable_html(
                product_name=payload.get("product_name") or order.get("title") or product.name,
                deliverable_name=product.deliverable_name,
                order_id=order_id,
                report_markdown=report_md,
                metrics=None,
                methodology={
                    "agents": f"{len(REVIEW_PANEL)} 位市场/合规评审",
                    "rounds": "评审面板逐项审查",
                    "scenario_label": product.name,
                },
                language=language,
            )
            save_deliverable(order_id, deliverable)

            result = {
                "report_id": None,
                "deliverable_url": f"/api/orders/{order_id}/deliverable",
                "metrics_summary": {
                    "overall_score": overall,
                    "reviewers": len(REVIEW_PANEL),
                    "risks_total": sum(
                        len(r.get("risks") or []) for r in outcome.get("panel_reviews", [])
                    ),
                },
            }
            self.store.set_result(order_id, result)
            logger.info(f"评审单 {order_id} 交付完成")

            base_url = f"https://{Config.CORS_ORIGINS}" if Config.CORS_ORIGINS not in ("*", "") else "http://localhost:5001"
            email_service.send_order_completed(
                order_id=order_id,
                user_email=order.get("user_email") or "",
                title=order.get("title") or product.name,
                deliverable_url=f"{base_url}{result['deliverable_url']}",
                language=language,
            )
            heartbeat_stop.set()

        except SimulationCancelled:
            heartbeat_stop.set()
            raise
        except Exception:
            heartbeat_stop.set()
            raise

    def _execute_order(self, order: Dict[str, Any], product, language: str = "zh") -> None:
        order_id = order["order_id"]
        payload = order.get("payload") or {}
        scenario_name = order.get("scenario") or product.scenario
        scenario = None
        from .scenarios import get_scenario as _get_scenario
        scenario = _get_scenario(scenario_name)
        requirement = compile_requirement(scenario_name, payload)
        budget = product.budget or {}
        max_agents = budget.get("max_agents")
        max_rounds = budget.get("max_rounds")
        deadline = time.time() + max(600, product.sla_minutes * 60)
        heartbeat_stop = threading.Event()

        def heartbeat_loop():
            while not heartbeat_stop.wait(HEARTBEAT_INTERVAL_SECONDS):
                try:
                    self.store.heartbeat(order_id)
                except Exception:
                    pass

        self.store.mark_running(order_id)
        threading.Thread(target=heartbeat_loop, daemon=True).start()
        logger.info(f"开始执行订单 {order_id}（{product.name}）")

        project_id = None
        simulation_id = None
        graph_id = None
        report = None
        try:
            # ── 1. 项目 + 种子资料 ────────────────────────────
            self._check_cancelled(order_id)
            project = ProjectManager.create_project(name=order.get("title") or product.name)
            project_id = project.project_id
            project.simulation_requirement = requirement
            project.scenario = scenario_name
            document_texts = []
            all_text = ""
            for file_info in order.get("files") or []:
                path = file_info["path"]
                if not os.path.exists(path):
                    continue
                text = TextProcessor.preprocess_text(FileParser.extract_text(path))
                document_texts.append(text)
                all_text += f"\n\n=== {file_info.get('original_name', 'seed')} ===\n{text}"
            if document_texts:
                project.files = [
                    {"filename": f.get("original_name", f["path"])}
                    for f in (order.get("files") or [])
                ]
                project.total_text_length = len(all_text)
                ProjectManager.save_extracted_text(project_id, all_text)
            ProjectManager.save_project(project)
            self._progress(order_id, 5, "project", f"项目 {project_id} 就绪，资料 {len(document_texts)} 份")

            # ── 2. 本体生成 ───────────────────────────────────
            self._check_cancelled(order_id)
            ontology = OntologyGenerator(scenario=scenario).generate(
                document_texts=document_texts or [requirement],
                simulation_requirement=requirement,
            )
            project.ontology = {
                "entity_types": ontology.get("entity_types", []),
                "edge_types": ontology.get("edge_types", []),
            }
            project.analysis_summary = ontology.get("analysis_summary", "")
            project.status = ProjectStatus.ONTOLOGY_GENERATED
            ProjectManager.save_project(project)
            self._progress(order_id, 15, "ontology",
                           f"本体 {len(project.ontology['entity_types'])} 个实体类型")

            # ── 3. 图谱构建 ───────────────────────────────────
            self._check_cancelled(order_id)
            builder = GraphBuilderService()
            graph_id = builder.create_graph(
                name=f"order-{order_id}",
                graph_id_callback=lambda gid: (
                    setattr(project, 'graph_id', gid),
                    ProjectManager.save_project(project),
                ),
            )
            builder.set_ontology(graph_id, project.ontology)
            chunks = TextProcessor.split_text(all_text or requirement,
                                              chunk_size=500, overlap=50)
            builder.validate_batch_chunks(chunks, batch_size=350)
            total_chunks = len(chunks)

            def graph_progress(msg, prog):
                self._progress(order_id, 15 + int(prog * 25), "graph",
                               f"图谱摄取 {int(prog * 100)}%")

            builder.add_text_batches(
                graph_id, chunks, batch_size=350, progress_callback=graph_progress,
            )
            graph_data = builder.get_graph_data(graph_id)
            project.status = ProjectStatus.GRAPH_COMPLETED
            ProjectManager.save_project(project)
            self._progress(order_id, 40, "graph",
                           f"图谱完成：{graph_data['node_count']} 节点 / {graph_data['edge_count']} 边")

            # ── 4. 模拟准备（人设 + 配置）─────────────────────
            self._check_cancelled(order_id)
            manager = SimulationManager()
            state = manager.create_simulation(
                project_id=project_id,
                graph_id=graph_id,
                enable_twitter=True,
                enable_reddit=True,
                scenario=scenario_name,
            )
            simulation_id = state.simulation_id

            def prepare_progress(stage, progress, message, **kwargs):
                overall = 40 + int(progress * 0.32)
                self._progress(order_id, overall, "prepare",
                               f"[{stage}] {message}")

            state = manager.prepare_simulation(
                simulation_id=simulation_id,
                simulation_requirement=requirement,
                document_text=all_text or requirement,
                use_llm_for_profiles=True,
                progress_callback=prepare_progress,
                parallel_profile_count=5,
                scenario=scenario,
                max_agents=max_agents,
            )
            if state.status == SimulationStatus.FAILED:
                raise RuntimeError(state.error or "模拟准备失败")
            self._progress(order_id, 72, "prepare",
                           f"准备完成：{state.profiles_count} 个 Agent")

            # ── 5. 双平台模拟 ─────────────────────────────────
            self._check_cancelled(order_id)
            SimulationRunner.start_simulation(
                simulation_id=simulation_id,
                platform="parallel",
                max_rounds=max_rounds,  # 成本护栏：SKU 预算的轮数上限
                enable_graph_memory_update=False,  # 商业单默认不回写图谱
            )
            self.store.update_progress(order_id, 72, "simulate", "模拟启动")

            close_env_sent = False
            while True:
                self._check_cancelled(order_id)
                run_state = SimulationRunner.get_run_state(simulation_id)
                status = getattr(run_state, "runner_status", None)
                if status in (RunnerStatus.COMPLETED, RunnerStatus.STOPPED):
                    break
                if status == RunnerStatus.FAILED:
                    raise RuntimeError(
                        getattr(run_state, "error", None) or "模拟执行失败"
                    )
                # 平台全部自然结束后，OASIS 子进程会停留在"等待命令模式"
                # （环境保留给 Interview）。订单场景无需 Interview，
                # 发送 close_env 让子进程优雅退出 → runner 进入 COMPLETED。
                # 按 enable 标志判断（兼容未来单平台模拟）。
                all_done = (
                    (run_state.twitter_completed or not state.enable_twitter)
                    and (run_state.reddit_completed or not state.enable_reddit)
                )
                if not close_env_sent and all_done:
                    try:
                        SimulationRunner.close_simulation_env(simulation_id)
                        close_env_sent = True
                        logger.info(f"已发送 close_env: {simulation_id}")
                    except Exception as close_error:
                        logger.warning(f"close_env 发送失败（将继续轮询）: {close_error}")
                        close_env_sent = True  # 避免重复发送
                if time.time() > deadline:
                    SimulationRunner.stop_simulation(simulation_id)
                    raise RuntimeError(
                        f"超过交付时限（SLA {product.sla_minutes} 分钟），模拟已终止"
                    )
                detail = {
                    "round": getattr(run_state, "twitter_current_round", 0) or 0,
                    "total_rounds": getattr(run_state, "total_rounds", 0) or 0,
                    "actions": getattr(run_state, "twitter_actions_count", 0) or 0,
                }
                round_ratio = detail["round"] / max(detail["total_rounds"], 1)
                self.store.update_progress(
                    order_id, min(88, 72 + int(round_ratio * 16)),
                    "simulate",
                    f"第 {detail['round']}/{detail['total_rounds']} 轮，动作 {detail['actions']}",
                )
                time.sleep(SIM_POLL_INTERVAL_SECONDS)

            run_state = SimulationRunner.get_run_state(simulation_id)
            rounds_done = getattr(run_state, "twitter_current_round", 0) or 0
            self._progress(order_id, 88, "simulate", f"模拟完成（{rounds_done} 轮）")

            # ── 6. 市场指标 ───────────────────────────────────
            self._check_cancelled(order_id)
            metrics = MarketMetricsService().compute_metrics(simulation_id, classify=True)
            self._progress(order_id, 90, "metrics", "市场指标计算完成")

            # ── 7. 报告 ───────────────────────────────────────
            self._check_cancelled(order_id)
            report_id = f"report_{uuid.uuid4().hex[:12]}"

            def report_progress(stage, progress, message):
                self._progress(order_id, 90 + int(progress * 0.07), "report", message)

            agent = ReportAgent(
                graph_id=graph_id,
                simulation_id=simulation_id,
                simulation_requirement=requirement,
                scenario=scenario,
                extra_supplement=product.report_supplement,
            )
            report = agent.generate_report(progress_callback=report_progress, report_id=report_id)
            from .models.task import TaskManager  # noqa: F401 - 报告内部使用
            from .services.report_agent import ReportManager
            ReportManager.save_report(report)
            if report.status.value != "completed":
                raise RuntimeError(report.error or "报告生成未完成")
            self._progress(order_id, 97, "report", "报告生成完成")

            # ── 8. 交付物 ─────────────────────────────────────
            deliverable = build_deliverable_html(
                product_name=payload.get("product_name") or order.get("title") or product.name,
                deliverable_name=product.deliverable_name,
                order_id=order_id,
                report_markdown=report.markdown_content,
                metrics=metrics,
                methodology={
                    "agents": state.profiles_count,
                    "rounds": rounds_done,
                    "scenario_label": product.name,
                },
            )
            save_deliverable(order_id, deliverable)

            result = {
                "report_id": report_id,
                "simulation_id": simulation_id,
                "project_id": project_id,
                "deliverable_url": f"/api/orders/{order_id}/deliverable",
                "report_url": f"/api/report/{report_id}",
                "metrics_summary": {
                    "totals": metrics.get("totals", {}),
                    "surveys": len(metrics.get("surveys") or []),
                },
            }
            self.store.set_result(order_id, result)
            logger.info(f"订单 {order_id} 交付完成: report={report_id}")

            # ── 邮件通知 ──────────────────────────────────────
            base_url = f"https://{Config.CORS_ORIGINS}" if Config.CORS_ORIGINS not in ("*", "") else "http://localhost:5001"
            email_service.send_order_completed(
                order_id=order_id,
                user_email=order.get("user_email") or "",
                title=order.get("title") or product.name,
                deliverable_url=f"{base_url}{result['deliverable_url']}",
                report_url=f"{base_url}{result.get('report_url', '')}" if result.get("report_url") else "",
                language=(order.get("payload") or {}).get("language", "zh"),
                metrics_summary=result.get("metrics_summary"),
            )
            heartbeat_stop.set()

        except SimulationCancelled:
            heartbeat_stop.set()
            if simulation_id:
                try:
                    SimulationRunner.stop_simulation(simulation_id)
                except Exception:
                    pass
            raise
        except Exception as e:
            heartbeat_stop.set()
            if simulation_id:
                try:
                    SimulationRunner.stop_simulation(simulation_id)
                except Exception:
                    pass
            raise
        finally:
            heartbeat_stop.set()


def main():
    parser = argparse.ArgumentParser(description="MiroFish 平台 Worker")
    parser.add_argument('--worker-id', default=f"worker_{uuid.uuid4().hex[:6]}")
    parser.add_argument('--concurrency', type=int, default=Config.WORKER_CONCURRENCY)
    parser.add_argument('--poll-interval', type=int, default=Config.WORKER_POLL_INTERVAL)
    parser.add_argument('--once', action='store_true', help='处理一单后退出（验收用）')
    args = parser.parse_args()

    setup_logger('mirofish')
    set_locale('zh')
    ProductManager.ensure_seeded()

    worker = OrderWorker(worker_id=args.worker_id,
                         concurrency=args.concurrency,
                         poll_interval=args.poll_interval)

    if args.once:
        result = worker.run_once()
        if result is None:
            print("没有待处理订单")
            return
        print(f"订单 {result['order_id']} 终态: {result['status']}")
        if result.get("error"):
            print(f"错误: {result['error']}")
        if result.get("result"):
            print(f"交付物: {result['result'].get('deliverable_url')}")
    else:
        try:
            worker.run_forever()
        except KeyboardInterrupt:
            worker.stop()
            logger.info("Worker 已停止")


if __name__ == "__main__":
    main()
