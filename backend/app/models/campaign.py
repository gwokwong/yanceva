"""Campaign（对比预演计划）模型与持久化。

一个 Campaign 基于一次基线模拟，克隆出多个变体模拟（改价格、换 KOL、
调整上市节奏等），串行运行后对比各自的市场指标，回答"哪种方案更好"。

变体克隆不调用 LLM：直接复制基线的人设与模拟配置文件，仅对配置做
override 改写，把对比成本控制在模拟本身的消耗上。
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger('mirofish.campaign')

# Campaign 状态
CAMPAIGN_CREATED = "created"
CAMPAIGN_RUNNING = "running"
CAMPAIGN_COMPLETED = "completed"
CAMPAIGN_FAILED = "failed"


@dataclass
class CampaignVariant:
    """一个对比变体：克隆自基线模拟并施加 overrides"""
    variant_id: str
    label: str
    simulation_id: str
    overrides: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CampaignVariant':
        return cls(
            variant_id=data['variant_id'],
            label=data.get('label', ''),
            simulation_id=data['simulation_id'],
            overrides=data.get('overrides', {}),
        )


@dataclass
class Campaign:
    """对比预演计划"""
    campaign_id: str
    name: str
    base_simulation_id: str
    scenario: str
    variants: List[CampaignVariant] = field(default_factory=list)
    status: str = CAMPAIGN_CREATED
    error: Optional[str] = None
    run_task_id: Optional[str] = None
    # 每个变体模拟的运行状态 {simulation_id: "running/completed/stopped/failed"}
    run_status: Dict[str, str] = field(default_factory=dict)
    # 成本护栏：变体模拟的最大轮数（None = 用模拟配置自身的时长）
    max_rounds: Optional[int] = None
    # 对比报告（LLM 生成的 markdown 与生成时间）
    comparison_report: Optional[Dict[str, Any]] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Campaign':
        return cls(
            campaign_id=data['campaign_id'],
            name=data.get('name', ''),
            base_simulation_id=data['base_simulation_id'],
            scenario=data.get('scenario', 'public_opinion'),
            variants=[CampaignVariant.from_dict(v) for v in data.get('variants', [])],
            status=data.get('status', CAMPAIGN_CREATED),
            error=data.get('error'),
            run_task_id=data.get('run_task_id'),
            run_status=data.get('run_status', {}),
            max_rounds=data.get('max_rounds'),
            comparison_report=data.get('comparison_report'),
            created_at=data.get('created_at', datetime.now().isoformat()),
            updated_at=data.get('updated_at', datetime.now().isoformat()),
        )


class CampaignManager:
    """Campaign 持久化管理（uploads/campaigns/<campaign_id>/campaign.json）"""

    CAMPAIGNS_DIR = os.path.join(Config.UPLOAD_FOLDER, 'campaigns')

    @classmethod
    def _ensure_dir(cls) -> None:
        os.makedirs(cls.CAMPAIGNS_DIR, exist_ok=True)

    @classmethod
    def _campaign_path(cls, campaign_id: str) -> str:
        return os.path.join(cls.CAMPAIGNS_DIR, campaign_id, 'campaign.json')

    @classmethod
    def create_campaign(
        cls,
        name: str,
        base_simulation_id: str,
        scenario: str,
        variants: List[CampaignVariant],
        max_rounds: Optional[int] = None,
    ) -> Campaign:
        campaign_id = f"camp_{uuid.uuid4().hex[:12]}"
        campaign = Campaign(
            campaign_id=campaign_id,
            name=name,
            base_simulation_id=base_simulation_id,
            scenario=scenario,
            variants=variants,
            max_rounds=max_rounds,
        )
        cls.save_campaign(campaign)
        return campaign

    @classmethod
    def save_campaign(cls, campaign: Campaign) -> None:
        cls._ensure_dir()
        os.makedirs(os.path.dirname(cls._campaign_path(campaign.campaign_id)), exist_ok=True)
        campaign.updated_at = datetime.now().isoformat()
        with open(cls._campaign_path(campaign.campaign_id), 'w', encoding='utf-8') as f:
            json.dump(campaign.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def get_campaign(cls, campaign_id: str) -> Optional[Campaign]:
        path = cls._campaign_path(campaign_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return Campaign.from_dict(data)
        except (OSError, ValueError, KeyError) as e:
            logger.error(f"读取 Campaign 失败: {campaign_id}, {e}")
            return None

    @classmethod
    def list_campaigns(cls) -> List[Campaign]:
        cls._ensure_dir()
        campaigns: List[Campaign] = []
        if not os.path.isdir(cls.CAMPAIGNS_DIR):
            return campaigns
        for entry in sorted(os.listdir(cls.CAMPAIGNS_DIR)):
            campaign = cls.get_campaign(entry)
            if campaign is not None:
                campaigns.append(campaign)
        campaigns.sort(key=lambda c: c.created_at, reverse=True)
        return campaigns

    @classmethod
    def delete_campaign(cls, campaign_id: str) -> bool:
        path = os.path.join(cls.CAMPAIGNS_DIR, campaign_id)
        if not os.path.isdir(path):
            return False
        import shutil
        shutil.rmtree(path, ignore_errors=True)
        return True
