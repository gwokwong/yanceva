"""场景包、市场指标、Campaign 变体与定时事件注入的单元测试。"""

import json
import os

import pytest

from app.scenarios import DEFAULT_SCENARIO, get_scenario
from app.scenarios.base import UnknownScenarioError
from app.services.market_metrics_service import MarketMetricsService
from app.services.simulation_manager import filter_and_cap_entities
from app.services.simulation_config_generator import SimulationConfigGenerator
from app.services.oasis_profile_generator import OasisProfileGenerator
from app.services.zep_entity_reader import EntityNode, FilteredEntities


# ============== 场景注册表 ==============

def test_default_scenario_is_public_opinion():
    assert DEFAULT_SCENARIO == "public_opinion"
    scenario = get_scenario(None)
    assert scenario.name == "public_opinion"


def test_unknown_scenario_raises():
    with pytest.raises(UnknownScenarioError):
        get_scenario("no_such_scenario")


def test_ecommerce_scenario_entity_roles():
    scenario = get_scenario("ecommerce")

    # 发声主体
    for agent_type in ("Consumer", "KOLInfluencer", "BrandOfficial", "CompetitorBrand"):
        assert scenario.is_agent_entity(agent_type), agent_type
    # 知识节点不生成 Agent
    for node_type in ("Product", "Promotion"):
        assert scenario.is_knowledge_node(node_type)
        assert not scenario.is_agent_entity(node_type)
    # 默认 Agent 上限与截断优先级
    assert scenario.default_max_agents == 60
    assert scenario.agent_priority
    assert scenario.scheduled_events_enabled is True


def test_opinion_scenario_has_no_scheduled_events():
    scenario = get_scenario("public_opinion")
    assert scenario.scheduled_events_enabled is False


def test_persona_prompts_use_scenario_templates():
    generator = OasisProfileGenerator(api_key="test-key", scenario=get_scenario("ecommerce"))
    prompt = generator._build_individual_persona_prompt(
        entity_name="小米耳机14",
        entity_type="Consumer",
        entity_summary="一位通勤白领",
        entity_attributes={},
        context="",
    )
    # 电商人设模板包含消费特征维度
    assert "消费特征" in prompt
    assert "价格敏感度" in prompt
    assert "小米耳机14" in prompt

    opinion = OasisProfileGenerator(api_key="test-key", scenario=get_scenario("public_opinion"))
    opinion_prompt = opinion._build_individual_persona_prompt(
        entity_name="张三",
        entity_type="Student",
        entity_summary="学生",
        entity_attributes={},
        context="",
    )
    # 舆情模板保持原有结构
    assert "个人记忆" in opinion_prompt
    assert "MBTI" in opinion_prompt


def test_config_generator_uses_scenario_prompts():
    generator = SimulationConfigGenerator(api_key="test-key", scenario=get_scenario("ecommerce"))
    prompt = generator.scenario.time_config_prompt.format(
        context_truncated="ctx", max_agents_allowed=10
    )
    assert "上市节奏" in prompt or "首销" in prompt

    opinion_prompt = get_scenario("public_opinion").time_config_prompt.format(
        context_truncated="ctx", max_agents_allowed=10
    )
    assert "peak_hours" in opinion_prompt


# ============== 实体过滤与数量上限 ==============

def _entity(name, etype, uuid=None):
    return EntityNode(
        uuid=uuid or f"uuid-{name}",
        name=name,
        labels=[etype],
        summary="",
        attributes={},
    )


def test_filter_and_cap_entities_drops_knowledge_nodes():
    scenario = get_scenario("ecommerce")
    filtered = FilteredEntities(
        entities=[
            _entity("降噪耳机X", "Product"),
            _entity("首发优惠", "Promotion"),
            _entity("张三", "Consumer"),
            _entity("数码博主李四", "KOLInfluencer"),
        ],
        entity_types={"Product", "Promotion", "Consumer", "KOLInfluencer"},
        total_count=4,
        filtered_count=4,
    )

    result = filter_and_cap_entities(filtered, scenario, max_agents=None)

    names = {e.name for e in result.entities}
    assert names == {"张三", "数码博主李四"}
    assert result.filtered_count == 2


def test_filter_and_cap_entities_prioritizes_by_role():
    scenario = get_scenario("ecommerce")
    consumers = [_entity(f"消费者{i}", "Consumer") for i in range(50)]
    kols = [_entity(f"KOL{i}", "KOLInfluencer") for i in range(5)]
    entities = consumers + kols

    filtered = FilteredEntities(
        entities=entities,
        entity_types={"Consumer", "KOLInfluencer"},
        total_count=len(entities),
        filtered_count=len(entities),
    )

    result = filter_and_cap_entities(filtered, scenario, max_agents=20)

    names = {e.name for e in result.entities}
    # KOL 全部保留，消费者抽样补足
    assert all(f"KOL{i}" in names for i in range(5))
    assert result.filtered_count == 20


def test_opinion_scenario_does_not_cap():
    scenario = get_scenario("public_opinion")
    entities = [_entity(f"P{i}", "Person") for i in range(100)]
    filtered = FilteredEntities(
        entities=entities,
        entity_types={"Person"},
        total_count=100,
        filtered_count=100,
    )

    result = filter_and_cap_entities(filtered, scenario, max_agents=None)
    assert result.filtered_count == 100


# ============== 市场指标服务 ==============

def _write_actions_log(sim_dir, platform, rows):
    os.makedirs(os.path.join(sim_dir, platform), exist_ok=True)
    with open(os.path.join(sim_dir, platform, "actions.jsonl"), "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_sim_config(sim_dir, config):
    with open(os.path.join(sim_dir, "simulation_config.json"), "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False)


def _base_config():
    return {
        "scenario": "ecommerce",
        "simulation_requirement": "降噪耳机新品上市预演",
        "event_config": {
            "hot_topics": ["降噪耳机X", "249元定价"],
            "initial_posts": [],
            "scheduled_events": [],
        },
        "agent_configs": [
            {"agent_id": 1, "entity_type": "Consumer", "entity_name": "张三"},
            {"agent_id": 2, "entity_type": "Consumer", "entity_name": "李四"},
            {"agent_id": 3, "entity_type": "KOLInfluencer", "entity_name": "博主"},
        ],
    }


def test_metrics_rule_series_and_keyword_hits(tmp_path, monkeypatch):
    sim_id = "sim-metrics-test"
    sim_dir = os.path.join(str(tmp_path), sim_id)
    os.makedirs(sim_dir, exist_ok=True)
    monkeypatch.setattr(
        "app.config.Config.OASIS_SIMULATION_DATA_DIR", str(tmp_path)
    )

    _write_sim_config(sim_dir, _base_config())
    _write_actions_log(sim_dir, "twitter", [
        {"round": 1, "event_type": "round_start", "simulated_hour": 20},
        {"round": 1, "agent_id": 1, "agent_name": "张三", "action_type": "CREATE_POST",
         "action_args": {"content": "这个降噪耳机X 249元定价值不值？"}},
        {"round": 1, "agent_id": 2, "agent_name": "李四", "action_type": "CREATE_COMMENT",
         "action_args": {"content": "好贵，等等降价再买"}},
        {"round": 1, "event_type": "round_end", "actions_count": 2},
    ])
    _write_actions_log(sim_dir, "reddit", [
        {"round": 2, "agent_id": 3, "agent_name": "博主", "action_type": "CREATE_POST",
         "action_args": {"content": "竞品对比：降噪耳机X vs 同期产品评测"}},
    ])

    service = MarketMetricsService()
    metrics = service.compute_metrics(sim_id)

    series = metrics["series"]
    assert [s["round"] for s in series] == [1, 2]
    round1 = series[0]
    assert round1["posts"] == 1
    assert round1["comments"] == 1
    assert round1["active_agents"] == 2
    assert round1["simulated_hour"] == 20
    assert round1["keyword_hits"]["price"] >= 1
    assert round1["keyword_hits"]["purchase"] >= 1
    round2 = series[1]
    assert round2["keyword_hits"]["competitor"] >= 1
    # 未分类时情绪/购买意愿为空
    assert round1["sentiment_avg"] is None

    # 增量：重复调用不会重复计数
    metrics_again = service.compute_metrics(sim_id)
    assert metrics_again["totals"]["posts"] == 2


def test_survey_probe_uses_scenario_template(tmp_path, monkeypatch):
    sim_id = "sim-survey-test"
    sim_dir = os.path.join(str(tmp_path), sim_id)
    os.makedirs(sim_dir, exist_ok=True)
    monkeypatch.setattr(
        "app.config.Config.OASIS_SIMULATION_DATA_DIR", str(tmp_path)
    )

    _write_sim_config(sim_dir, _base_config())

    captured = {}

    def fake_interview(simulation_id, interviews, platform=None, timeout=None):
        captured["interviews"] = interviews
        return {
            "success": True,
            "results": {
                f"reddit_{i}": {"agent_id": item["agent_id"], "response": "会买 4分", "platform": "reddit"}
                for i, item in enumerate(interviews)
            },
        }

    from app.services import market_metrics_service as module

    monkeypatch.setattr(
        "app.services.simulation_runner.SimulationRunner.interview_agents_batch",
        staticmethod(fake_interview),
    )

    service = module.MarketMetricsService()
    survey = service.run_survey_probe(sim_id, sample_size=2, current_round=10)

    assert captured["interviews"]
    # 只抽样消费者类 Agent（survey_target_types）
    agent_ids = {item["agent_id"] for item in captured["interviews"]}
    assert agent_ids <= {1, 2}
    assert survey["sample_size"] == 2
    assert len(survey["responses"]) == 2


def test_report_summary_renders_series(tmp_path, monkeypatch):
    sim_id = "sim-summary-test"
    sim_dir = os.path.join(str(tmp_path), sim_id)
    os.makedirs(sim_dir, exist_ok=True)
    monkeypatch.setattr(
        "app.config.Config.OASIS_SIMULATION_DATA_DIR", str(tmp_path)
    )
    _write_sim_config(sim_dir, _base_config())
    _write_actions_log(sim_dir, "twitter", [
        {"round": 1, "agent_id": 1, "agent_name": "张三", "action_type": "CREATE_POST",
         "action_args": {"content": "249元的价格可以接受，准备买"}},
    ])

    service = MarketMetricsService()
    assert "暂无市场指标数据" in service.get_report_summary(sim_id)

    service.compute_metrics(sim_id)
    summary = service.get_report_summary(sim_id)
    assert "市场指标摘要" in summary
    assert "| 1 |" in summary


# ============== Campaign 变体改写 ==============

def test_apply_variant_overrides_content_replacement():
    from app.api.campaign import apply_variant_overrides

    config = {
        "simulation_requirement": "定价249元的新品上市预演",
        "agent_configs": [
            {"agent_id": 1, "entity_type": "BrandOfficial"},
            {"agent_id": 2, "entity_type": "KOLInfluencer"},
        ],
        "event_config": {
            "initial_posts": [
                {"content": "官宣：新品售价249元", "poster_type": "BrandOfficial", "poster_agent_id": 1}
            ],
            "scheduled_events": [
                {"content": "首销开售，249元到手", "poster_type": "BrandOfficial",
                 "poster_agent_id": 1, "trigger_round": 40, "event_name": "首销"}
            ],
        },
        "product_name": "新品249款",
    }

    overrides = {"content_replacements": {"249": "199"}}
    result = apply_variant_overrides(json.loads(json.dumps(config)), overrides)

    assert "199" in result["simulation_requirement"]
    assert result["event_config"]["initial_posts"][0]["content"] == "官宣：新品售价199元"
    assert result["event_config"]["scheduled_events"][0]["content"] == "首销开售，199元到手"
    assert result["product_name"] == "新品199款"


def test_apply_variant_overrides_scheduled_events_and_kol():
    from app.api.campaign import apply_variant_overrides

    config = {
        "simulation_requirement": "req",
        "agent_configs": [
            {"agent_id": 1, "entity_type": "BrandOfficial", "influence_weight": 2.0,
             "activity_level": 0.5, "posts_per_hour": 0.4},
            {"agent_id": 2, "entity_type": "Consumer", "influence_weight": 1.0},
            {"agent_id": 3, "entity_type": "CompetitorBrand", "influence_weight": 2.4},
        ],
        "event_config": {},
    }

    result = apply_variant_overrides(config, {
        "scheduled_events": [
            {"content": "竞品降价50元", "poster_type": "competitorbrand", "trigger_round": "50"}
        ],
        "kol_agent_ids": [1],
    })

    events = result["event_config"]["scheduled_events"]
    assert len(events) == 1
    assert events[0]["poster_agent_id"] == 3  # competitorbrand 匹配到 CompetitorBrand Agent
    assert events[0]["trigger_round"] == 50

    brand = next(c for c in result["agent_configs"] if c["agent_id"] == 1)
    assert brand["influence_weight"] == 3.0  # 2.0 * 1.5
    assert brand["activity_level"] == 0.6
    consumer = next(c for c in result["agent_configs"] if c["agent_id"] == 2)
    assert consumer["influence_weight"] == 1.0  # 未受影响


# ============== 定时事件注入（脚本层） ==============

def test_build_scheduled_event_actions_triggers_on_matching_round():
    from scripts.run_parallel_simulation import build_scheduled_event_actions

    logs = []

    class Logger:
        def log_action(self, **kwargs):
            logs.append(kwargs)

    class Agent:
        pass

    class AgentGraph:
        def get_agent(self, agent_id):
            return Agent()

    class Env:
        agent_graph = AgentGraph()

    class Result:
        env = Env()

    config = {
        "event_config": {
            "scheduled_events": [
                {"content": "首销开售", "poster_agent_id": 3, "trigger_round": 40, "event_name": "首销"},
                {"content": "竞品降价", "poster_agent_id": 4, "trigger_round": 60, "event_name": "竞品反击"},
            ]
        }
    }

    result = Result()

    actions = build_scheduled_event_actions(
        config, 39, result, {3: "官方号"}, Logger(), lambda m: None, logged_round=40
    )
    assert len(actions) == 1
    assert logs[0]["round_num"] == 40
    assert logs[0]["action_args"]["content"] == "首销开售"
    assert logs[0]["result"].startswith("[scheduled_event]")

    # 未到触发轮 → 无注入
    assert build_scheduled_event_actions(
        config, 39, result, {3: "官方号"}, Logger(), lambda m: None, logged_round=39
    ) == {}

    # 无事件配置 → 零影响
    assert build_scheduled_event_actions(
        {"event_config": {}}, 40, result, {}, Logger(), lambda m: None
    ) == {}
