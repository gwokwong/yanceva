"""场景（Scenario）注册表。

MiroFish 的六段流水线（本体 → 图谱 → 人设 → 模拟 → 指标 → 报告）通过
Scenario 对象获取各阶段的 prompt、实体角色规则与指标配置，替代原先
硬编码的"社交媒体舆论模拟"单一场景。

- ``public_opinion``：原舆情场景的等价迁移（默认场景，行为不变）
- ``ecommerce``：电商新品上市预演场景

Scenario 数据结构定义在 ``app/scenarios/base.py``；
新增场景只需新建一个 ``Scenario`` 实例并注册到 ``SCENARIOS``。
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .base import (  # noqa: F401 - 对外统一从 app.scenarios 导入
    DEFAULT_SCENARIO,
    Scenario,
    UnknownScenarioError,
)

SCENARIOS: Dict[str, Scenario] = {}


def register_scenario(scenario: Scenario) -> None:
    SCENARIOS[scenario.name] = scenario


def get_scenario(name: Optional[str]) -> Scenario:
    """按名称取场景；名称为空时回退默认场景。"""

    if name:
        scenario = SCENARIOS.get(name)
        if scenario is not None:
            return scenario
        raise UnknownScenarioError(
            f"未知场景 '{name}'，可用场景: {sorted(SCENARIOS)}"
        )
    return SCENARIOS[DEFAULT_SCENARIO]


def list_scenarios() -> List[Dict[str, str]]:
    """返回全部场景的名称与 i18n 键（供前端选择器使用）。"""

    return [
        {"name": s.name, "label_key": s.label_key, "description_key": s.description_key}
        for s in SCENARIOS.values()
    ]


# 注册内置场景
from .public_opinion import PUBLIC_OPINION_SCENARIO  # noqa: E402
from .ecommerce import ECOMMERCE_SCENARIO  # noqa: E402
from .saas_pricing import SAAS_PRICING_SCENARIO  # noqa: E402
from .brand_crisis import BRAND_CRISIS_SCENARIO  # noqa: E402
from .competitor_response import COMPETITOR_RESPONSE_SCENARIO  # noqa: E402
from .creator_content import CREATOR_CONTENT_SCENARIO  # noqa: E402
from .listing_review import LISTING_REVIEW_SCENARIO  # noqa: E402

register_scenario(PUBLIC_OPINION_SCENARIO)
register_scenario(ECOMMERCE_SCENARIO)
register_scenario(SAAS_PRICING_SCENARIO)
register_scenario(BRAND_CRISIS_SCENARIO)
register_scenario(COMPETITOR_RESPONSE_SCENARIO)
register_scenario(CREATOR_CONTENT_SCENARIO)
register_scenario(LISTING_REVIEW_SCENARIO)
