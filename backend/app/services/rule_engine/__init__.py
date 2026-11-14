"""模块 A：规则引擎五步算法（纯计算，不写库）。

对外只暴露三样东西：
- `generate_plan(profile, request, data_source)`：五步算法入口；
- `SqlDataSource(session)` / `CsvDishSource(path)`：数据装配；
- 数据模型（`Profile` / `PlanRequest` / `PlanResult`）。
"""
from .balance import apply_balance, build_micro_hints, compute_balance
from .candidates import build_candidates, diversify, hard_filter_reasons
from .errors import HardConstraintUnsatisfiable, InsufficientData, RuleEngineError
from .models import (
    Candidate,
    DishFacts,
    DishPortion,
    KEY_MICRONUTRIENTS,
    MealTarget,
    PlanRequest,
    PlanResult,
    Profile,
    SlotResult,
    Targets,
)
from .pipeline import generate_plan, plan_dates
from .repository import CsvDishSource, RuleEngineDataSource, SqlDataSource
from .targets import bmr_mifflin, compute_targets, parse_goal_policy

__all__ = [
    "generate_plan",
    "plan_dates",
    "compute_targets",
    "parse_goal_policy",
    "bmr_mifflin",
    "build_candidates",
    "diversify",
    "hard_filter_reasons",
    "compute_balance",
    "apply_balance",
    "build_micro_hints",
    "SqlDataSource",
    "CsvDishSource",
    "RuleEngineDataSource",
    "Profile",
    "PlanRequest",
    "PlanResult",
    "SlotResult",
    "Candidate",
    "DishFacts",
    "DishPortion",
    "MealTarget",
    "Targets",
    "KEY_MICRONUTRIENTS",
    "RuleEngineError",
    "HardConstraintUnsatisfiable",
    "InsufficientData",
]
