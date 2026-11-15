"""场景（Scenario）定义的数据结构与查询辅助。

MiroFish 的六段流水线（本体 → 图谱 → 人设 → 模拟 → 指标 → 报告）通过
Scenario 对象获取各阶段的 prompt、实体角色规则与指标配置，替代原先
硬编码的"社交媒体舆论模拟"单一场景。

注册表与默认场景见 ``app/scenarios/__init__.py``。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_SCENARIO = "public_opinion"


class UnknownScenarioError(ValueError):
    """Raised when a scenario name is not registered."""


@dataclass(frozen=True)
class Scenario:
    """一个模拟场景的全链路配置。"""

    name: str
    # 前端 i18n 键
    label_key: str
    description_key: str

    # ── 本体生成 ──────────────────────────────────────────────
    # 本体系统提示词正文（语言指令与 PascalCase 约束由生成器统一追加）
    ontology_system_prompt: str
    # 用户消息尾部的"必须遵守的规则"块
    ontology_user_rules: str

    # ── Persona 生成 ─────────────────────────────────────────
    persona_system_prompt: str
    individual_persona_prompt: str
    group_persona_prompt: str
    # 可发声实体类型白名单（个人/群体），只有这些类型会生成 Agent
    individual_entity_types: Tuple[str, ...]
    group_entity_types: Tuple[str, ...]
    # 仅作为图谱知识节点存在的类型（不生成 Agent）
    knowledge_node_types: Tuple[str, ...] = ()
    # max_agents 截断时的类型优先级（越靠前越优先保留）
    agent_priority: Tuple[str, ...] = ()
    # 场景默认 Agent 数量上限（None = 不限制）
    default_max_agents: Optional[int] = None

    # 规则兜底人设：[(匹配类型集合, 人设字典), ...]（LLM 失败时的降级）
    rule_persona_profiles: Tuple[Tuple[Tuple[str, ...], Dict[str, Any]], ...] = ()

    # ── 模拟配置生成 ─────────────────────────────────────────
    time_config_prompt: str = ""
    time_config_system_prompt: str = ""
    default_time_config: Dict[str, Any] = field(default_factory=dict)
    event_config_prompt: str = ""
    event_config_system_prompt: str = ""
    agent_config_prompt: str = ""
    agent_config_system_prompt: str = ""
    # 规则兜底行为配置：[(匹配类型集合, 配置字典), ...]
    rule_agent_configs: Tuple[Tuple[Tuple[str, ...], Dict[str, Any]], ...] = ()
    # poster_type 别名映射（LLM 输出容错）
    type_aliases: Dict[str, List[str]] = field(default_factory=dict)
    # 是否让 LLM 生成 scheduled_events（模拟中途定时事件）
    scheduled_events_enabled: bool = False

    # ── 市场指标 ─────────────────────────────────────────────
    # 静态指标关键词（产品名/竞品名等动态关键词在运行时由配置补充）
    metric_keywords: Dict[str, List[str]] = field(default_factory=dict)
    # 问卷探针模板（{product_name} 占位）
    survey_template: str = ""
    # 消费者类实体类型（问卷抽样对象）
    survey_target_types: Tuple[str, ...] = ()

    # ── 报告生成 ─────────────────────────────────────────────
    # 注入 PLAN/SECTION 系统 prompt 的场景化补充（为空则完全等价原行为）
    report_plan_supplement: str = ""
    report_section_supplement: str = ""

    # ── Campaign 变量说明 ────────────────────────────────────
    campaign_overrides_doc: str = ""

    # ── 查询辅助 ─────────────────────────────────────────────

    def agent_entity_types(self) -> Tuple[str, ...]:
        """所有可生成 Agent 的实体类型（小写）。"""

        return tuple(
            t.lower() for t in (*self.individual_entity_types, *self.group_entity_types)
        )

    def is_agent_entity(self, entity_type: Optional[str]) -> bool:
        return (entity_type or "").lower() in self.agent_entity_types()

    def is_knowledge_node(self, entity_type: Optional[str]) -> bool:
        return (entity_type or "").lower() in {
            t.lower() for t in self.knowledge_node_types
        }

    def find_rule_persona(self, entity_type: str) -> Optional[Dict[str, Any]]:
        """按类型查找规则兜底人设（小写匹配，返回首个命中的副本）。"""

        lowered = (entity_type or "").lower()
        for types, profile in self.rule_persona_profiles:
            if lowered in {t.lower() for t in types}:
                return dict(profile)
        return None

    def find_rule_agent_config(self, entity_type: str) -> Optional[Dict[str, Any]]:
        """按类型查找规则兜底行为配置（小写匹配）。"""

        lowered = (entity_type or "").lower()
        for types, config in self.rule_agent_configs:
            if lowered in {t.lower() for t in types}:
                return dict(config)
        return None

    def get_metric_keywords(self) -> Dict[str, List[str]]:
        """返回场景静态指标关键词的副本。"""

        return {k: list(v) for k, v in self.metric_keywords.items()}
