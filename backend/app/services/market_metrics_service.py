"""市场信号层：电商新品上市预演的指标提取服务。

从模拟产生的 ``actions.jsonl`` 中增量提取市场指标：
- 规则指标（零 LLM 成本）：每轮发帖/评论量、活跃 Agent 数、价格/购买/
  质量/竞品类关键词命中
- LLM 分类（可选、抽样、缓存）：对含产品提及的内容做情绪与购买意愿分类
- 问卷探针：抽样采访消费者 Agent，获取"购买意愿/心理价位/主要顾虑"

结果持久化到 ``uploads/simulations/<sim_id>/market_metrics.json``，
ReportAgent 的 ``market_metrics`` 工具与前端指标面板共用此数据。
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..config import Config
from ..scenarios import get_scenario, Scenario
from ..utils.logger import get_logger
from ..utils.llm_client import LLMClient

logger = get_logger('mirofish.market_metrics')

# 文本内容字段到动作类型的映射（用于提取讨论文本）
_CONTENT_FIELDS = ("content", "original_content", "quote_content", "comment_content")

# 每次分类调用最多条数与单次最多新增分类条数（资源保护）
CLASSIFY_BATCH_SIZE = 25
CLASSIFY_MAX_NEW_PER_CALL = 60

# 锁：metrics 文件为单进程内共享状态
_metrics_locks: Dict[str, threading.Lock] = {}
_metrics_locks_guard = threading.Lock()


def _metrics_lock(simulation_id: str) -> threading.Lock:
    with _metrics_locks_guard:
        return _metrics_locks.setdefault(simulation_id, threading.Lock())


class MarketMetricsService:
    """从模拟行为日志中提取市场指标。"""

    def __init__(self, scenario: Optional[Scenario] = None):
        self._scenario = scenario
        self._llm_client: Optional[LLMClient] = None

    def _get_llm(self) -> LLMClient:
        if self._llm_client is None:
            # 轻量分类调用：显式 120s 超时，避免端点挂起拖垮整个订单
            self._llm_client = LLMClient(timeout=120.0)
        return self._llm_client

    # ------------------------------------------------------------------
    # 文件路径
    # ------------------------------------------------------------------

    @staticmethod
    def _sim_dir(simulation_id: str) -> str:
        return os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)

    @classmethod
    def _metrics_path(cls, simulation_id: str) -> str:
        return os.path.join(cls._sim_dir(simulation_id), "market_metrics.json")

    @classmethod
    def _state_path(cls, simulation_id: str) -> str:
        return os.path.join(cls._sim_dir(simulation_id), "metrics_state.json")

    @classmethod
    def _config_path(cls, simulation_id: str) -> str:
        return os.path.join(cls._sim_dir(simulation_id), "simulation_config.json")

    # ------------------------------------------------------------------
    # 配置加载
    # ------------------------------------------------------------------

    def _load_config(self, simulation_id: str) -> Dict[str, Any]:
        try:
            with open(self._config_path(simulation_id), 'r', encoding='utf-8') as f:
                return json.load(f) or {}
        except (OSError, ValueError):
            return {}

    def _get_scenario(self, config: Dict[str, Any]) -> Scenario:
        if self._scenario is not None:
            return self._scenario
        try:
            return get_scenario(config.get("scenario"))
        except Exception:
            return get_scenario(None)

    def _dynamic_keywords(self, config: Dict[str, Any], scenario: Scenario) -> Dict[str, List[str]]:
        """合并场景静态关键词与运行时动态关键词（产品名/热点话题）。"""

        keywords = scenario.get_metric_keywords()
        event_config = config.get("event_config") or {}
        hot_topics = [str(t) for t in (event_config.get("hot_topics") or []) if t]
        # 热点话题（通常含产品名、卖点、竞品名）同时计入 product 类命中
        if hot_topics:
            keywords.setdefault("product", [])
            keywords["product"] = keywords["product"] + hot_topics

        # Campaign 变体可注入 metrics_keywords 覆盖
        override = config.get("metrics_keywords") or {}
        for key, words in override.items():
            keywords[key] = list(words) + keywords.get(key, [])
        return keywords

    # ------------------------------------------------------------------
    # 增量解析
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_text(action_args: Dict[str, Any]) -> str:
        if not isinstance(action_args, dict):
            return ""
        for field_name in _CONTENT_FIELDS:
            value = action_args.get(field_name)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _parse_platform_log(
        self,
        platform: str,
        log_path: str,
        offset: int,
        keyword_map: Dict[str, List[str]],
    ) -> Dict[str, Any]:
        """解析单个平台的 actions.jsonl 增量段。

        Returns:
            {"offset": 新的文件偏移, "rounds": {round: 统计}, "texts": [待分类文本]}
        """

        rounds: Dict[int, Dict[str, Any]] = {}
        texts: List[Dict[str, Any]] = []
        new_offset = offset

        lowered_keywords = {
            key: [w.lower() for w in words]
            for key, words in keyword_map.items()
        }

        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                if offset:
                    f.seek(offset)
                lines = f.readlines()
                new_offset = f.tell()
        except OSError:
            return {"offset": offset, "rounds": rounds, "texts": texts}

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue

            # 事件行（round_start/round_end 等）只用于补充 simulated_hour
            if entry.get("event_type"):
                if entry.get("event_type") == "round_start":
                    rnd = int(entry.get("round", 0) or 0)
                    bucket = rounds.setdefault(rnd, self._empty_round_bucket(rnd))
                    hour = entry.get("simulated_hour")
                    if hour is not None:
                        bucket["simulated_hour"] = int(hour)
                continue

            action_type = (entry.get("action_type") or "").upper()
            rnd = int(entry.get("round", 0) or 0)
            bucket = rounds.setdefault(rnd, self._empty_round_bucket(rnd))
            bucket["actions"] += 1

            if action_type == "CREATE_POST":
                bucket["posts"] += 1
            elif action_type == "CREATE_COMMENT":
                bucket["comments"] += 1
            elif action_type in ("LIKE_POST", "LIKE_COMMENT", "DISLIKE_POST", "DISLIKE_COMMENT"):
                bucket["likes"] += 1
            elif action_type in ("REPOST", "QUOTE_POST"):
                bucket["reposts"] += 1

            agent_id = entry.get("agent_id")
            if agent_id is not None:
                bucket["agent_ids"].add(int(agent_id))

            content = self._extract_text(entry.get("action_args") or {})
            if not content:
                continue
            bucket["content_items"] += 1

            content_lower = content.lower()
            for key, words in lowered_keywords.items():
                if any(word and word in content_lower for word in words):
                    bucket["keyword_hits"][key] = bucket["keyword_hits"].get(key, 0) + 1

            texts.append({
                "platform": platform,
                "round": rnd,
                "agent_id": entry.get("agent_id"),
                "content": content,
                "sha1": hashlib.sha1(content.encode("utf-8")).hexdigest(),
            })

        return {"offset": new_offset, "rounds": rounds, "texts": texts}

    @staticmethod
    def _empty_round_bucket(rnd: int) -> Dict[str, Any]:
        return {
            "round": rnd,
            "simulated_hour": None,
            "actions": 0,
            "posts": 0,
            "comments": 0,
            "likes": 0,
            "reposts": 0,
            "content_items": 0,
            "agent_ids": set(),
            "keyword_hits": {},
        }

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def compute_metrics(
        self,
        simulation_id: str,
        classify: bool = False,
        classify_limit: int = CLASSIFY_MAX_NEW_PER_CALL,
    ) -> Dict[str, Any]:
        """增量解析模拟日志并返回累计指标（写回 market_metrics.json）。"""

        with _metrics_lock(simulation_id):
            metrics = self._load_metrics(simulation_id)
            state = self._load_state(simulation_id)
            config = self._load_config(simulation_id)
            scenario = self._get_scenario(config)
            keyword_map = self._dynamic_keywords(config, scenario)

            merged_rounds: Dict[int, Dict[str, Any]] = {
                int(item.get("round", 0) or 0): {
                    **item,
                    "agent_ids": set(item.get("agent_ids", [])),
                }
                for item in metrics.get("series", [])
            }

            all_new_texts: List[Dict[str, Any]] = []

            for platform in ("twitter", "reddit"):
                log_path = os.path.join(self._sim_dir(simulation_id), platform, "actions.jsonl")
                if not os.path.exists(log_path):
                    continue
                offset = int(state.get("offsets", {}).get(platform, 0) or 0)
                parsed = self._parse_platform_log(platform, log_path, offset, keyword_map)

                state.setdefault("offsets", {})[platform] = parsed["offset"]

                for rnd_str, bucket in parsed["rounds"].items():
                    existing = merged_rounds.get(rnd_str)
                    if existing is None:
                        merged_rounds[rnd_str] = bucket
                    else:
                        for key in ("actions", "posts", "comments", "likes", "reposts", "content_items"):
                            existing[key] = existing.get(key, 0) + bucket.get(key, 0)
                        existing["agent_ids"] |= bucket["agent_ids"]
                        if bucket.get("simulated_hour") is not None:
                            existing["simulated_hour"] = bucket["simulated_hour"]
                        hits = dict(existing.get("keyword_hits") or {})
                        for key, count in bucket.get("keyword_hits", {}).items():
                            hits[key] = hits.get(key, 0) + count
                        existing["keyword_hits"] = hits

                all_new_texts.extend(parsed["texts"])

            # LLM 分类（可选）—— 直接更新 metrics 内的 classifications，
            # 避免内部重新加载导致最终写盘覆盖分类结果
            classifications = metrics.setdefault("classifications", {})
            if classify and all_new_texts:
                self._classify_texts(all_new_texts, classifications, limit=classify_limit)

            # 分类结果聚合到各轮
            by_round: Dict[int, List[Dict[str, Any]]] = {}
            for item in classifications.values():
                by_round.setdefault(int(item.get("round", 0) or 0), []).append(item)

            series = []
            for rnd in sorted(merged_rounds):
                bucket = merged_rounds[rnd]
                classified = by_round.get(rnd, [])
                sentiments = [
                    c["sentiment"] for c in classified
                    if isinstance(c.get("sentiment"), (int, float))
                ]
                intents = [
                    c["purchase_intent"] for c in classified
                    if isinstance(c.get("purchase_intent"), (int, float))
                ]
                series.append({
                    "round": rnd,
                    "simulated_hour": bucket.get("simulated_hour"),
                    "actions": bucket.get("actions", 0),
                    "posts": bucket.get("posts", 0),
                    "comments": bucket.get("comments", 0),
                    "likes": bucket.get("likes", 0),
                    "reposts": bucket.get("reposts", 0),
                    "active_agents": len(bucket.get("agent_ids", set())),
                    "content_items": bucket.get("content_items", 0),
                    "keyword_hits": bucket.get("keyword_hits", {}),
                    "classified_count": len(classified),
                    "sentiment_avg": round(sum(sentiments) / len(sentiments), 3) if sentiments else None,
                    "purchase_intent_avg": (
                        round(sum(intents) / len(intents), 3) if intents else None
                    ),
                })

            totals = {
                "rounds": len(series),
                "actions": sum(s["actions"] for s in series),
                "posts": sum(s["posts"] for s in series),
                "comments": sum(s["comments"] for s in series),
                "keyword_hits": {},
                "classified_count": len(classifications),
                "survey_count": len(metrics.get("surveys", [])),
            }
            for s in series:
                for key, count in (s.get("keyword_hits") or {}).items():
                    totals["keyword_hits"][key] = totals["keyword_hits"].get(key, 0) + count

            metrics.update({
                "simulation_id": simulation_id,
                "scenario": scenario.name,
                "updated_at": datetime.now().isoformat(),
                "series": series,
                "totals": totals,
            })

            self._save_metrics(simulation_id, metrics)
            self._save_state(simulation_id, state)
            return metrics

    # ------------------------------------------------------------------
    # LLM 分类
    # ------------------------------------------------------------------

    CLASSIFY_SYSTEM_PROMPT = (
        "你是电商市场信号分析器。给定一组社交媒体帖子/评论，对每条内容分类，"
        '输出JSON对象 {"items": [{"id": <输入序号>, "sentiment": <-1.0负面到1.0正面>, '
        '"purchase_intent": <0.0到1.0，购买意愿强度>, '
        '"topics": ["price"|"quality"|"competitor"|"other"中最多两个]}]}。'
        "只输出该JSON对象，不要其他内容。"
    )

    def _classify_texts(
        self,
        texts: List[Dict[str, Any]],
        classifications: Dict[str, Dict[str, Any]],
        limit: int = CLASSIFY_MAX_NEW_PER_CALL,
    ) -> None:
        """对未分类的内容做 LLM 情绪/购买意愿分类（带缓存与上限）。

        直接更新调用方传入的 ``classifications`` 字典（与最终持久化共享
        同一份数据，避免覆盖丢失）。"""

        pending: List[Dict[str, Any]] = []
        seen: set = set()
        for item in texts:
            sha1 = item["sha1"]
            if sha1 in classifications or sha1 in seen:
                continue
            seen.add(sha1)
            pending.append(item)
        if not pending:
            return

        # 抽样上限：优先最新内容
        pending = pending[-limit:] if limit and len(pending) > limit else pending

        llm = self._get_llm()
        for start in range(0, len(pending), CLASSIFY_BATCH_SIZE):
            batch = pending[start:start + CLASSIFY_BATCH_SIZE]
            user_lines = "\n".join(
                f"{index}. [{item['platform']} r{item['round']}] {item['content'][:300]}"
                for index, item in enumerate(batch, 1)
            )
            prompt = (
                "请对以下内容逐条分类：\n"
                f"{user_lines}\n\n"
                '输出JSON数组，例如：[{"id": 1, "sentiment": 0.5, '
                '"purchase_intent": 0.8, "topics": ["price"]}]'
            )
            try:
                result = llm.chat_json(
                    messages=[
                        {"role": "system", "content": self.CLASSIFY_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.1,
                    max_attempts=1,
                )
            except Exception as error:
                logger.warning(f"市场指标 LLM 分类失败（跳过本批）: {error}")
                continue

            items = result if isinstance(result, list) else result.get("items") or []  # 兼容对象/数组两种返回
            by_id = {}
            for entry in items:
                if isinstance(entry, dict) and "id" in entry:
                    try:
                        by_id[int(entry["id"])] = entry
                    except (TypeError, ValueError):
                        continue

            for index, item in enumerate(batch, 1):
                entry = by_id.get(index)
                if not entry:
                    continue
                try:
                    sentiment = max(-1.0, min(1.0, float(entry.get("sentiment", 0))))
                except (TypeError, ValueError):
                    sentiment = 0.0
                try:
                    intent = max(0.0, min(1.0, float(entry.get("purchase_intent", 0))))
                except (TypeError, ValueError):
                    intent = 0.0
                topics = [
                    t for t in (entry.get("topics") or [])
                    if isinstance(t, str) and t in ("price", "quality", "competitor", "other")
                ]
                classifications[item["sha1"]] = {
                    "text": item["content"][:300],
                    "platform": item["platform"],
                    "round": item["round"],
                    "agent_id": item["agent_id"],
                    "sentiment": sentiment,
                    "purchase_intent": intent,
                    "topics": topics,
                }

    # ------------------------------------------------------------------
    # 问卷探针
    # ------------------------------------------------------------------

    def run_survey_probe(
        self,
        simulation_id: str,
        sample_size: int = 15,
        current_round: Optional[int] = None,
    ) -> Dict[str, Any]:
        """抽样采访消费者 Agent，收集购买意愿/心理价位/主要顾虑。"""

        config = self._load_config(simulation_id)
        scenario = self._get_scenario(config)

        agent_configs = config.get("agent_configs") or []
        target_types = {t.lower() for t in scenario.survey_target_types} or {"consumer", "person"}
        candidates = [
            cfg for cfg in agent_configs
            if (cfg.get("entity_type") or "").lower() in target_types
        ]
        if not candidates:
            candidates = agent_configs
        if not candidates:
            raise ValueError("模拟配置中没有可采访的 Agent")

        sample_size = max(1, min(int(sample_size), len(candidates), 20))  # 资源保护
        sampled = random.sample(candidates, sample_size)

        product_name = config.get("product_name") or "本次新品"
        template = scenario.survey_template or (
            "假设{product_name}已经上市开售：你会购买吗（1-5分）？"
            "心理价位多少？主要顾虑是什么？"
        )
        prompt = template.format(product_name=product_name)

        # 复用现有 IPC 采访机制
        from .simulation_runner import SimulationRunner
        interviews = [
            {"agent_id": cfg["agent_id"], "prompt": prompt}
            for cfg in sampled
            if cfg.get("agent_id") is not None
        ]
        result = SimulationRunner.interview_agents_batch(
            simulation_id=simulation_id,
            interviews=interviews,
            platform=None,
            timeout=180,
        )

        responses = []
        raw_results = (result or {}).get("results") or {}
        for key, item in raw_results.items():
            if not isinstance(item, dict):
                continue
            responses.append({
                "agent_id": item.get("agent_id"),
                "platform": item.get("platform", key.split("_", 1)[0]),
                "response": (item.get("response") or "")[:500],
            })

        survey_entry = {
            "timestamp": datetime.now().isoformat(),
            "round": current_round,
            "prompt": prompt,
            "sample_size": len(responses),
            "responses": responses,
        }

        with _metrics_lock(simulation_id):
            metrics = self._load_metrics(simulation_id)
            surveys = metrics.setdefault("surveys", [])
            surveys.append(survey_entry)
            metrics["updated_at"] = datetime.now().isoformat()
            totals = metrics.get("totals") or {}
            totals["survey_count"] = len(surveys)
            metrics["totals"] = totals
            self._save_metrics(simulation_id, metrics)

        return survey_entry

    # ------------------------------------------------------------------
    # 报告工具摘要
    # ------------------------------------------------------------------

    def get_report_summary(self, simulation_id: str) -> str:
        """为 ReportAgent 的 market_metrics 工具生成文本摘要。"""

        metrics = self._load_metrics(simulation_id)
        if not metrics.get("series"):
            return "（暂无市场指标数据：模拟尚未产生行为日志，或指标尚未计算）"

        series = metrics["series"]
        totals = metrics.get("totals") or {}

        lines = ["## 市场指标摘要（按模拟轮次）", ""]
        lines.append(
            "| round | 发帖 | 评论 | 活跃Agent | 情绪均值 | 购买意愿均值 | 价格词命中 |"
        )
        lines.append("|---|---|---|---|---|---|---|")
        for s in series[-30:]:  # 最近30轮，控制上下文长度
            sentiment = "—" if s.get("sentiment_avg") is None else f"{s['sentiment_avg']:+.2f}"
            intent = "—" if s.get("purchase_intent_avg") is None else f"{s['purchase_intent_avg']:.2f}"
            price_hits = (s.get("keyword_hits") or {}).get("price", 0)
            lines.append(
                f"| {s['round']} | {s['posts']} | {s['comments']} | "
                f"{s['active_agents']} | {sentiment} | {intent} | {price_hits} |"
            )

        lines.append("")
        lines.append(f"累计：发帖 {totals.get('posts', 0)} 条，评论 {totals.get('comments', 0)} 条；"
                     f"关键词命中：{json.dumps(totals.get('keyword_hits', {}), ensure_ascii=False)}")

        surveys = metrics.get("surveys") or []
        if surveys:
            latest = surveys[-1]
            lines.append("")
            lines.append(
                f"最近问卷探针（round {latest.get('round')}，样本 {latest.get('sample_size')} 人）："
            )
            for response in (latest.get("responses") or [])[:8]:
                answer = (response.get("response") or "").replace("\n", " ")[:200]
                lines.append(f"- Agent#{response.get('agent_id')}: {answer}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------

    def _load_metrics(self, simulation_id: str) -> Dict[str, Any]:
        try:
            with open(self._metrics_path(simulation_id), 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    data.setdefault("series", [])
                    data.setdefault("classifications", {})
                    data.setdefault("surveys", [])
                    return data
        except (OSError, ValueError):
            pass
        return {"series": [], "classifications": {}, "surveys": []}

    def _save_metrics(self, simulation_id: str, metrics: Dict[str, Any]) -> None:
        os.makedirs(self._sim_dir(simulation_id), exist_ok=True)
        with open(self._metrics_path(simulation_id), 'w', encoding='utf-8') as f:
            json.dump(metrics, f, ensure_ascii=False, indent=2)

    def _load_state(self, simulation_id: str) -> Dict[str, Any]:
        try:
            with open(self._state_path(simulation_id), 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except (OSError, ValueError):
            pass
        return {"offsets": {}}

    def _save_state(self, simulation_id: str, state: Dict[str, Any]) -> None:
        os.makedirs(self._sim_dir(simulation_id), exist_ok=True)
        with open(self._state_path(simulation_id), 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)


def get_market_metrics_service() -> MarketMetricsService:
    """进程共享的服务实例（无状态，直接新建亦可）。"""
    return MarketMetricsService()
