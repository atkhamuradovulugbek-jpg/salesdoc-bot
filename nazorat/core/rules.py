"""
rules.py — config/rules.yaml va config/agents.yaml'ni o'qib, pydantic bilan tekshiradi.
Barcha biznes raqamlar shu ikkita fayldan keladi.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

CONFIG_DIR = Path(__file__).parent.parent / "config"


class BallStep(BaseModel):
    min_pct: float
    ball: int


class ToyTier(BaseModel):
    blocks: float
    bonus: int


class CommissionStep(BaseModel):
    min_sales: float
    pct: float


class PlanBonusStep(BaseModel):
    min_pct: float
    bonus: int


class PodiumRules(BaseModel):
    prizes: list[int]
    min_over: int = 1
    no_repeat_first: bool = True


class GrowthRules(BaseModel):
    prize: int
    min_pct: float = 10
    no_repeat: bool = True


class ToyRules(BaseModel):
    sku_ids: list[str]
    units_per_block: int = 24
    tiers: list[ToyTier]


class AlertRules(BaseModel):
    dead_days_zero_ball: int = 2


class Rules(BaseModel):
    timezone: str = "Asia/Tashkent"
    sunday_off: bool = True
    statuses_ok: list[int] = Field(default_factory=lambda: [1, 2, 3])
    status_full_return: int = 4
    daily_plan: dict[str, float]            # league -> so'm
    ball_scale: list[BallStep]
    returns_reduce_ball: bool = True
    monthly_sales_plan: dict[str, float]    # league -> so'm
    podium: PodiumRules
    growth: GrowthRules
    toy: ToyRules
    kpi_commission: dict[str, list[CommissionStep]]
    kpi_plan_bonus: dict[str, list[PlanBonusStep]]
    debt_limit: dict[str, float]
    alerts: AlertRules = Field(default_factory=AlertRules)


class Agent(BaseModel):
    sd_id: str
    name: str                                # to'liq ism (Sales Doctor'dagi)
    display: str = ""                        # qisqa ism (ballplan ro'yxatidagi)
    area: str = ""
    league: str                              # city / region
    code: str
    ball_plan: int = 0
    observe_only: bool = False               # yangi agent: ball bor, plan/sovrin yo'q
    debt_limit: float | None = None          # alohida limit (bo'lmasa liga standarti)

    @property
    def short(self) -> str:
        return self.display or (self.name.split()[0] if " " in self.name else self.name)


class Supervisor(BaseModel):
    code: str
    name: str
    league: str


class AgentsConfig(BaseModel):
    agents: list[Agent]
    supervisors: list[Supervisor] = Field(default_factory=list)


def load_rules(path: Path | None = None) -> Rules:
    p = path or (CONFIG_DIR / "rules.yaml")
    with open(p, encoding="utf-8") as f:
        return Rules.model_validate(yaml.safe_load(f))


def load_agents(path: Path | None = None) -> AgentsConfig:
    p = path or (CONFIG_DIR / "agents.yaml")
    with open(p, encoding="utf-8") as f:
        return AgentsConfig.model_validate(yaml.safe_load(f))
