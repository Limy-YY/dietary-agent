"""规则引擎五步算法的纯计算数据模型。

设计约束（与《后端接口契约 v1.2-r2》《任务书 v1.2 模块 A》一致）：
- 只做确定性计算，不含 LLM、不含数据库访问；
- 所有缺失值用 None 表示，**不得当 0 参与判断**（null ≠ 0）；
- 字段名与数据库 v1.2 结构对齐（dish_id 为 text、油盐独立、微量为 nutrient_id 键）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------- 常量

#: 三大宏量的能量系数（kcal/g）
KCAL_PER_G = {"protein_g": 4.0, "fat_g": 9.0, "carb_g": 4.0}

#: 活动系数固定值（口径：BMR × 1.4，不再读 activity_level）
DEFAULT_ACTIVITY_FACTOR = 1.4

#: 默认每餐能量占比（早 30% / 午 40% / 晚 30%）
DEFAULT_MEAL_RATIOS: dict[str, float] = {"早": 0.3, "午": 0.4, "晚": 0.3}

#: 宏量区间容忍度（目标值 ±15%）
DEFAULT_MACRO_TOLERANCE = 0.15

#: 每日油盐糖上限（《中国居民膳食指南 2022》：油 25~30 g、盐 <5 g、添加糖 <25 g）
#: 数据库 goal_structure_map.oil_salt_sugar_policy 若给出更严值，以库值为准。
DEFAULT_DAILY_LIMITS = {"oil_g": 25.0, "salt_g": 5.0, "added_sugar_g": 25.0}

#: 7 种关键微量（与 app.v_key_micronutrient 的 nutrient_id / display_order 一致）
KEY_MICRONUTRIENTS: tuple[tuple[str, str, str], ...] = (
    ("calcium", "钙", "mg"),
    ("iron", "铁", "mg"),
    ("zinc", "锌", "mg"),
    ("vitamin_a", "维生素A", "μgRAE"),
    ("vitamin_b1", "维生素B1", "mg"),
    ("vitamin_b2", "维生素B2", "mg"),
    ("vitamin_c", "维生素C", "mg"),
)
MICRO_IDS: tuple[str, ...] = tuple(k for k, _, _ in KEY_MICRONUTRIENTS)
MICRO_NAME_ZH: dict[str, str] = {k: zh for k, zh, _ in KEY_MICRONUTRIENTS}
MICRO_UNIT: dict[str, str] = {k: u for k, _, u in KEY_MICRONUTRIENTS}
#: 与库内 core.nutrient.unit 对齐（维生素A 在库里写作「μg RAE」）
MICRO_UNIT["vitamin_a"] = "μg RAE"

#: 主食识别（core.dish.category 取值）
STAPLE_CATEGORY = "主食"
#: category 为空时的名称兜底关键词（v1.1 批 30 道菜 category 未回填，仅靠名称兜底）
STAPLE_NAME_HINTS: tuple[str, ...] = ("饭", "粥", "红薯", "馒头", "面条", "米粉")
#: 汤羹类别（只允许作为第二道菜，避免「汤 + 汤」）
SOUP_CATEGORY = "汤羹"

#: 宗教/伦理忌口关键词（名称命中即硬排除；用户 religious_ethical 取值需含左侧键）
RELIGIOUS_KEYWORDS: dict[str, tuple[str, ...]] = {
    "清真": ("猪", "五花", "培根", "火腿", "香肠", "腊肉", "排骨", "肉肠"),
    "伊斯兰": ("猪", "五花", "培根", "火腿", "香肠", "腊肉", "排骨", "肉肠"),
    "素食": ("鸡", "鸭", "猪", "牛", "羊", "鱼", "虾", "蟹", "蛤", "贝", "肉", "排骨", "培根", "火腿", "香肠"),
    "佛教": ("鸡", "鸭", "猪", "牛", "羊", "鱼", "虾", "蟹", "蛤", "贝", "肉", "排骨", "葱", "蒜", "韭"),
}

#: 做法所需的厨具（method_text 命中键 → 需要 cooking_equipment 含任一值）
METHOD_EQUIPMENT: dict[str, tuple[str, ...]] = {
    "蒸": ("蒸锅", "电饭煲", "炒锅"),
    "烤箱": ("烤箱", "空气炸锅"),
    "烤": ("烤箱", "空气炸锅"),
    "炖": ("炖锅", "电饭煲", "炒锅", "高压锅"),
    "焖": ("炒锅", "炖锅", "电饭煲"),
    "炒": ("炒锅",),
    "快炒": ("炒锅",),
    "煮": ("锅", "炒锅", "电饭煲"),
    "拌": (),
    "凉拌": (),
}


# ---------------------------------------------------------------- 输入模型


@dataclass(slots=True)
class Profile:
    """轻量档案（对应 app.profile 的可写字段）。"""

    gender: str = "女"
    age: int = 20
    height_cm: float = 160.0
    weight_kg: float = 55.0
    goal_code: str = "maintain"
    conditions: dict[str, dict[str, Any]] = field(default_factory=dict)
    allergies: list[str] = field(default_factory=list)
    religious_ethical: list[str] = field(default_factory=list)
    cooking_equipment: list[str] = field(default_factory=list)
    name: str | None = None

    @property
    def confirmed_conditions(self) -> list[str]:
        """仅 confirmed 状态参与规则（suspected / unknown 不参与）。"""
        return [
            cid
            for cid, payload in (self.conditions or {}).items()
            if isinstance(payload, dict) and payload.get("status") == "confirmed"
        ]


@dataclass(slots=True)
class GoalPolicy:
    """core.goal_structure_map 一行（只取计算需要的部分）。"""

    goal_code: str = "maintain"
    goal_name: str | None = None
    activity_factor: float = DEFAULT_ACTIVITY_FACTOR
    protein_pct: float = 0.20
    fat_pct: float = 0.25
    carb_pct: float = 0.55
    daily_limits: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_DAILY_LIMITS))
    oil_salt_strict: bool = False
    notes: list[str] = field(default_factory=list)

    def normalized(self) -> "GoalPolicy":
        """把三大宏量占比归一到 1.0；缺失或全 0 时退回默认 20/25/55。"""
        total = self.protein_pct + self.fat_pct + self.carb_pct
        if total <= 0:
            return GoalPolicy(
                goal_code=self.goal_code,
                goal_name=self.goal_name,
                activity_factor=self.activity_factor,
                protein_pct=0.20,
                fat_pct=0.25,
                carb_pct=0.55,
                daily_limits=self.daily_limits,
                oil_salt_strict=self.oil_salt_strict,
                notes=self.notes,
            )
        return GoalPolicy(
            goal_code=self.goal_code,
            goal_name=self.goal_name,
            activity_factor=self.activity_factor,
            protein_pct=self.protein_pct / total,
            fat_pct=self.fat_pct / total,
            carb_pct=self.carb_pct / total,
            daily_limits=self.daily_limits,
            oil_salt_strict=self.oil_salt_strict,
            notes=self.notes,
        )


@dataclass(slots=True)
class MicroReference:
    """一条微量参考值（RNI/AI/UL）。"""

    nutrient_id: str
    value: float | None
    unit: str = ""
    reference_type: str = "RNI"
    age_band: str | None = None
    note: str | None = None


@dataclass(slots=True)
class DishFacts:
    """一道菜的可计算事实（按当前食材事实表聚合，null 保持 None）。"""

    dish_id: str
    name: str
    category: str | None = None
    tags: list[str] = field(default_factory=list)
    method_text: str | None = None
    cooking_rule_id: str | None = None
    servings: float = 1.0
    default_oil_g: float | None = 0.0
    default_salt_g: float | None = 0.0
    cook_time_min: int | None = None
    energy_kcal: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    carb_g: float | None = None
    fiber_g: float | None = None
    sodium_mg: float | None = None
    calcium_mg: float | None = None
    micro: dict[str, float | None] = field(default_factory=dict)
    strict_allergens: list[str] = field(default_factory=list)
    unverified_food_ids: list[str] = field(default_factory=list)
    ingredient_names: list[str] = field(default_factory=list)
    source: str | None = None

    @property
    def is_staple(self) -> bool:
        """主食判定：category='主食' → tags 含「主食」→ category 缺失时名称兜底。"""
        category = (self.category or "").strip()
        if category == STAPLE_CATEGORY:
            return True
        if STAPLE_CATEGORY in [str(t) for t in (self.tags or [])]:
            return True
        if not category and any(hint in (self.name or "") for hint in STAPLE_NAME_HINTS):
            return True
        return False

    @property
    def is_soup(self) -> bool:
        return (self.category or "").strip() == SOUP_CATEGORY

    @property
    def allergen_unverified(self) -> bool:
        """存在「未核查」食材：不排除，但必须保留提示。"""
        return bool(self.unverified_food_ids)


@dataclass(slots=True)
class PlanRequest:
    """一次生成请求（用户自定范围）。"""

    start_date: str
    end_date: str
    plan_type: str = "日"
    meal_types: list[str] = field(default_factory=lambda: ["早", "午", "晚"])
    candidates_per_slot: int = 3
    goal_code: str | None = None
    user_id: str | None = None
    exclude_ingredients: list[str] = field(default_factory=list)
    soft_avoid: list[str] = field(default_factory=list)
    meal_ratios: dict[str, float] | None = None
    window_days: int = 7
    tolerance: float = DEFAULT_MACRO_TOLERANCE
    max_slots: int = 21


# ---------------------------------------------------------------- 输出模型


@dataclass(slots=True)
class MacroRange:
    """一个宏量项的区间与目标值。"""

    name: str
    target: float | None
    low: float | None
    high: float | None
    unit: str = "g"

    def contains(self, value: float | None) -> bool | None:
        """返回 None 表示无法判定（目标或实测缺失）。"""
        if value is None or self.low is None or self.high is None:
            return None
        return self.low <= value <= self.high

    def deviation(self, value: float | None) -> float | None:
        """相对目标的归一化偏差（0 表示正好命中）。"""
        if value is None or self.target is None or self.target == 0:
            return None
        return abs(value - self.target) / self.target


@dataclass(slots=True)
class MealTarget:
    """一餐的计算目标。"""

    meal_type: str
    ratio: float
    kcal: float
    protein: MacroRange
    fat: MacroRange
    carb: MacroRange
    oil_limit_g: float
    salt_limit_g: float
    added_sugar_limit_g: float
    micro: dict[str, float | None] = field(default_factory=dict)


@dataclass(slots=True)
class Targets:
    """第 1 步「算目标」的产物。"""

    bmr: float
    activity_factor: float
    energy_kcal: float
    goal_code: str
    goal_name: str | None
    goal_policy: GoalPolicy
    meal_targets: dict[str, MealTarget]
    micro_targets: dict[str, MicroReference]
    oil_salt_strict: bool = False
    hard_allergens: list[str] = field(default_factory=list)
    hard_religious: list[str] = field(default_factory=list)
    excluded_ingredients: list[str] = field(default_factory=list)
    equipment: list[str] = field(default_factory=list)
    confirmed_conditions: list[str] = field(default_factory=list)
    condition_note: list[str] = field(default_factory=list)
    micro_note: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "goal_code": self.goal_code,
            "goal_name": self.goal_name,
            "bmr": round(self.bmr, 1),
            "activity_factor": self.activity_factor,
            "energy_kcal": round(self.energy_kcal, 1),
            "macro_policy": {
                "protein_pct": round(self.goal_policy.protein_pct, 4),
                "fat_pct": round(self.goal_policy.fat_pct, 4),
                "carb_pct": round(self.goal_policy.carb_pct, 4),
            },
            "meal_targets": {
                mt: {
                    "kcal": round(t.kcal, 1),
                    "protein_g": [t.protein.low, t.protein.high],
                    "fat_g": [t.fat.low, t.fat.high],
                    "carb_g": [t.carb.low, t.carb.high],
                    "oil_limit_g": round(t.oil_limit_g, 2),
                    "salt_limit_g": round(t.salt_limit_g, 2),
                }
                for mt, t in self.meal_targets.items()
            },
            "micro_targets": {
                k: {"value": v.value, "unit": v.unit, "type": v.reference_type}
                for k, v in self.micro_targets.items()
            },
            "hard_constraints": {
                "allergens": self.hard_allergens,
                "religious_ethical": self.hard_religious,
                "excluded_ingredients": self.excluded_ingredients,
                "confirmed_conditions": self.confirmed_conditions,
            },
            "notes": self.micro_note + self.condition_note,
        }


@dataclass(slots=True)
class DishPortion:
    """候选中的一道菜（含份量与展示字段）。"""

    facts: DishFacts
    servings: float = 1.0

    @property
    def dish_id(self) -> str:
        return self.facts.dish_id

    @property
    def name(self) -> str:
        return self.facts.name

    @property
    def role(self) -> str:
        return "主食" if self.facts.is_staple else "菜"

    def scaled(self, value: float | None) -> float | None:
        if value is None:
            return None
        return value * self.servings

    def as_dict(self, display_order: int) -> dict[str, Any]:
        return {
            "dish_id": self.facts.dish_id,
            "name": self.facts.name,
            "role": self.role,
            "servings": round(self.servings, 2),
            "estimated_g": None,  # 由展示层按份量估算，计算层不编造
            "portion_text": _portion_text(self.facts, self.servings),
            "method_override": None,
            "display_order": display_order,
        }


@dataclass(slots=True)
class Candidate:
    """一个餐位候选（主食 + 1~2 道菜）。"""

    candidate_id: int
    rank: int
    portions: list[DishPortion]
    totals: dict[str, float | None]
    oil_salt: dict[str, float | None]
    micro_estimate: dict[str, float | None]
    score: float = 0.0
    reason_codes: list[str] = field(default_factory=list)
    why_text: str = ""
    eating_order_advice: str = ""
    notes: list[str] = field(default_factory=list)
    signature: tuple[str, ...] = ()

    @property
    def dish_ids(self) -> list[str]:
        return [p.dish_id for p in self.portions]

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "rank": self.rank,
            "why_text": self.why_text,
            "reason_codes": self.reason_codes,
            "macro_estimate": {
                "kcal": _round(self.totals.get("kcal")),
                "protein_g": _round(self.totals.get("protein_g")),
                "fat_g": _round(self.totals.get("fat_g")),
                "carb_g": _round(self.totals.get("carb_g")),
                "fiber_g": _round(self.totals.get("fiber_g")),
            },
            "micro_estimate": {k: _round(self.micro_estimate.get(k)) for k in MICRO_IDS},
            "oil_salt_estimate": {
                "oil_g": _round(self.oil_salt.get("oil_g")),
                "salt_g": _round(self.oil_salt.get("salt_g")),
            },
            "eating_order_advice": self.eating_order_advice,
            "sources": [{"type": "dish", "dish_id": d} for d in self.dish_ids],
            "dishes": [p.as_dict(i + 1) for i, p in enumerate(self.portions)],
        }


@dataclass(slots=True)
class MicroStatus:
    """某个微量的跨日平衡结论。"""

    nutrient_id: str
    name_zh: str
    unit: str
    target: float | None
    window_total: float | None
    window_days: int
    remaining: float | None
    covered_pct: float | None
    status: str
    note: str | None = None


@dataclass(slots=True)
class BalanceReport:
    """第 4 步「跨日平衡」的产物。"""

    window_start: str | None
    window_end: str | None
    window_days: int
    items: dict[str, MicroStatus]
    improvements: list[str] = field(default_factory=list)
    data_notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "window_start": self.window_start,
            "window_end": self.window_end,
            "window_days": self.window_days,
            "items": {
                k: {
                    "name_zh": v.name_zh,
                    "unit": v.unit,
                    "target": _round(v.target),
                    "window_total": _round(v.window_total),
                    "remaining": _round(v.remaining),
                    "covered_pct": _round(v.covered_pct),
                    "status": v.status,
                    "note": v.note,
                }
                for k, v in self.items.items()
            },
            "improvements": self.improvements,
            "data_notes": self.data_notes,
        }


@dataclass(slots=True)
class SlotResult:
    """一个餐位的生成结果。"""

    meal_type: str
    slot_date: str
    display_order: int
    target: MealTarget
    candidates: list[Candidate]
    selected_candidate_id: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "display_order": self.display_order,
            "meal_type": self.meal_type,
            "slot_date": self.slot_date,
            "target_macro": {
                "kcal": round(self.target.kcal, 1),
                "protein_g": _round(self.target.protein.target),
                "fat_g": _round(self.target.fat.target),
                "carb_g": _round(self.target.carb.target),
            },
            "selected_candidate_id": self.selected_candidate_id,
            "candidates": [c.as_dict() for c in self.candidates],
        }


@dataclass(slots=True)
class PlanResult:
    """第 5 步「输出」的完整结果（可直接映射为 MealCard payload）。"""

    plan_type: str
    start_date: str
    end_date: str
    status: str
    targets: Targets
    slots: list[SlotResult]
    balance: BalanceReport | None
    why_summary: str
    reference_hints: list[str] = field(default_factory=list)
    data_quality_notes: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "plan_type": self.plan_type,
            "status": self.status,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "goal_code": self.targets.goal_code,
            "goal_energy_kcal": round(self.targets.energy_kcal, 1),
            "macro_ratio": {k: v.ratio for k, v in self.targets.meal_targets.items()},
            "slots": [s.as_dict() for s in self.slots],
            "why_summary": self.why_summary,
            "reference_hints": self.reference_hints,
            "data_quality_notes": self.data_quality_notes,
            "balance": self.balance.as_dict() if self.balance else None,
            "diagnostics": self.diagnostics,
        }


# ---------------------------------------------------------------- 工具函数


def _round(value: float | None, digits: int = 1) -> float | None:
    """四舍五入并保留 None 语义（None 不进位、不当 0）。"""
    if value is None:
        return None
    return round(value, digits)


def _portion_text(facts: DishFacts, servings: float) -> str | None:
    """按份量给出比喻式估量；份量非整数或没有菜名时返回 None。"""
    if not facts.name:
        return None
    if servings == 1:
        return "1 份"
    if servings == 0.5:
        return "半份"
    if servings > 1:
        return f"{servings:g} 份"
    return None


def macro_gap(
    totals: dict[str, float | None],
    target: MealTarget,
) -> dict[str, float | None]:
    """计算候选与餐目标的宏量差（正值=超出，负值=不足，None=无法判定）。"""
    out: dict[str, float | None] = {}
    for key, rng in (
        ("protein_g", target.protein),
        ("fat_g", target.fat),
        ("carb_g", target.carb),
    ):
        value = totals.get(key)
        if value is None or rng.target is None:
            out[key] = None
        else:
            out[key] = round(value - rng.target, 1)
    kcal_value = totals.get("kcal")
    out["kcal"] = round(kcal_value - target.kcal, 1) if kcal_value is not None else None
    return out
