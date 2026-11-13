"""数据装配层：把数据库事实表转成 DishFacts / 目标 / 窗口余额。

为什么需要这一层（v1.2 的已知缺口）：
- `app.v_dish_live_nutrition` 只输出 energy_kcal / protein_g / sodium_mg / calcium_mg，
  没有 fat / carbohydrate / fiber 与 7 微量；而五步算法要用宏量区间和微量覆盖；
- 因此这里按 `core.dish_ingredient.amount_g × core.ingredient.* / 100` 自行聚合，
  并沿用与视图一致的 NULL 传播规则（任一食材缺值 → 整道菜为 NULL，绝不按 0 计）。

7 微量的取值位置（必须按库内真实结构取，不统一当 nutrient_id 键）：
- calcium      → `core.ingredient.calcium_mg` 列
- iron         → `micro_nutrients->>'iron_mg'`
- zinc         → `micro_nutrients->>'zinc_mg'`
- vitamin_a    → `micro_nutrients->>'vitamin_a_ug'`
- vitamin_b1   → `micro_nutrients->>'vitamin_b1_mg'`
- vitamin_b2   → `micro_nutrients->>'vitamin_b2_mg'`
- vitamin_c    → `micro_nutrients->>'vitamin_c_mg'`
"""
from __future__ import annotations

import csv
from collections.abc import Iterable, Sequence
from typing import Any, Protocol

from .models import DishFacts, Profile, MICRO_IDS

__all__ = [
    "RuleEngineDataSource",
    "SqlDataSource",
    "CsvDishSource",
    "MICRO_JSON_KEYS",
    "SEX_VARIANTS",
]

#: 微量 nutrient_id → core.ingredient.micro_nutrients 的键名
MICRO_JSON_KEYS: dict[str, str] = {
    "iron": "iron_mg",
    "zinc": "zinc_mg",
    "vitamin_a": "vitamin_a_ug",
    "vitamin_b1": "vitamin_b1_mg",
    "vitamin_b2": "vitamin_b2_mg",
    "vitamin_c": "vitamin_c_mg",
}

#: 性别取值兼容（库里可能是 男/女、male/female、both）
SEX_VARIANTS: dict[str, list[str]] = {
    "男": ["男", "male", "both", "unisex"],
    "女": ["女", "female", "both", "unisex"],
}


class RuleEngineDataSource(Protocol):
    """规则引擎所需的数据访问协议（Sql 与离线源都实现它）。"""

    def get_goal_row(self, goal_code: str) -> dict[str, Any] | None: ...

    def get_micro_reference_rows(self, profile: Profile) -> list[dict[str, Any]]: ...

    def get_dish_facts(self) -> list[DishFacts]: ...

    def get_micro_window(
        self, user_id: str, window_start: str, window_end: str
    ) -> list[dict[str, Any]]: ...


# ---------------------------------------------------------------- SQL 实现


_DISH_SQL = """
WITH base AS (
    SELECT
        d.dish_id, d.name, d.category, d.tags, d.method_text, d.cooking_rule_id,
        d.servings, d.default_oil_g, d.default_salt_g, d.cook_time_min, d.source,
        di.amount_g,
        i.name AS ingredient_name,
        i.food_id,
        i.energy_kcal, i.protein_g, i.fat_g, i.carbohydrate_g, i.fiber_g,
        i.sodium_mg, i.calcium_mg, i.allergens, i.allergen_status,
        (i.micro_nutrients->>'iron_mg')::numeric      AS iron_mg,
        (i.micro_nutrients->>'zinc_mg')::numeric      AS zinc_mg,
        (i.micro_nutrients->>'vitamin_a_ug')::numeric AS vitamin_a_ug,
        (i.micro_nutrients->>'vitamin_b1_mg')::numeric AS vitamin_b1_mg,
        (i.micro_nutrients->>'vitamin_b2_mg')::numeric AS vitamin_b2_mg,
        (i.micro_nutrients->>'vitamin_c_mg')::numeric AS vitamin_c_mg
    FROM core.dish d
    JOIN core.dish_ingredient di ON di.dish_id = d.dish_id
    JOIN core.ingredient i ON i.ingredient_id = di.ingredient_id
    WHERE NOT d.is_deleted AND NOT i.is_deleted
), agg AS (
    SELECT
        dish_id,
        count(*) AS ingredient_count,
        CASE WHEN count(*) FILTER (WHERE energy_kcal IS NULL OR amount_g IS NULL) > 0
             THEN NULL ELSE round(sum(amount_g * energy_kcal / 100.0), 1) END AS energy_kcal,
        CASE WHEN count(*) FILTER (WHERE protein_g IS NULL OR amount_g IS NULL) > 0
             THEN NULL ELSE round(sum(amount_g * protein_g / 100.0), 1) END AS protein_g,
        CASE WHEN count(*) FILTER (WHERE fat_g IS NULL OR amount_g IS NULL) > 0
             THEN NULL ELSE round(sum(amount_g * fat_g / 100.0), 1) END AS fat_g,
        CASE WHEN count(*) FILTER (WHERE carbohydrate_g IS NULL OR amount_g IS NULL) > 0
             THEN NULL ELSE round(sum(amount_g * carbohydrate_g / 100.0), 1) END AS carb_g,
        CASE WHEN count(*) FILTER (WHERE fiber_g IS NULL OR amount_g IS NULL) > 0
             THEN NULL ELSE round(sum(amount_g * fiber_g / 100.0), 1) END AS fiber_g,
        CASE WHEN count(*) FILTER (WHERE sodium_mg IS NULL OR amount_g IS NULL) > 0
             THEN NULL ELSE round(sum(amount_g * sodium_mg / 100.0), 1) END AS sodium_mg,
        CASE WHEN count(*) FILTER (WHERE calcium_mg IS NULL OR amount_g IS NULL) > 0
             THEN NULL ELSE round(sum(amount_g * calcium_mg / 100.0), 2) END AS calcium_mg,
        CASE WHEN count(*) FILTER (WHERE iron_mg IS NULL OR amount_g IS NULL) > 0
             THEN NULL ELSE round(sum(amount_g * iron_mg / 100.0), 2) END AS iron,
        CASE WHEN count(*) FILTER (WHERE zinc_mg IS NULL OR amount_g IS NULL) > 0
             THEN NULL ELSE round(sum(amount_g * zinc_mg / 100.0), 2) END AS zinc,
        CASE WHEN count(*) FILTER (WHERE vitamin_a_ug IS NULL OR amount_g IS NULL) > 0
             THEN NULL ELSE round(sum(amount_g * vitamin_a_ug / 100.0), 2) END AS vitamin_a,
        CASE WHEN count(*) FILTER (WHERE vitamin_b1_mg IS NULL OR amount_g IS NULL) > 0
             THEN NULL ELSE round(sum(amount_g * vitamin_b1_mg / 100.0), 3) END AS vitamin_b1,
        CASE WHEN count(*) FILTER (WHERE vitamin_b2_mg IS NULL OR amount_g IS NULL) > 0
             THEN NULL ELSE round(sum(amount_g * vitamin_b2_mg / 100.0), 3) END AS vitamin_b2,
        CASE WHEN count(*) FILTER (WHERE vitamin_c_mg IS NULL OR amount_g IS NULL) > 0
             THEN NULL ELSE round(sum(amount_g * vitamin_c_mg / 100.0), 2) END AS vitamin_c,
        COALESCE(array_agg(DISTINCT ingredient_name ORDER BY ingredient_name), ARRAY[]::text[]) AS ingredient_names,
        COALESCE(
            array_agg(DISTINCT allergen.alternative)
            FILTER (WHERE allergen_status = '已确认含' AND allergen.alternative IS NOT NULL),
            ARRAY[]::text[]
        ) AS strict_allergens,
        COALESCE(
            array_agg(DISTINCT food_id)
            FILTER (WHERE allergen_status = '未核查' AND food_id IS NOT NULL),
            ARRAY[]::text[]
        ) AS unverified_food_ids
    FROM base
    LEFT JOIN LATERAL unnest(base.allergens) AS allergen(alternative) ON true
    GROUP BY dish_id
)
SELECT
    d.dish_id, d.name, d.category, d.tags, d.method_text, d.cooking_rule_id,
    d.servings, d.default_oil_g, d.default_salt_g, d.cook_time_min, d.source,
    a.energy_kcal, a.protein_g, a.fat_g, a.carb_g, a.fiber_g, a.sodium_mg, a.calcium_mg,
    a.iron, a.zinc, a.vitamin_a, a.vitamin_b1, a.vitamin_b2, a.vitamin_c,
    a.ingredient_names, a.strict_allergens, a.unverified_food_ids
FROM core.dish d
JOIN agg a ON a.dish_id = d.dish_id
WHERE NOT d.is_deleted
ORDER BY d.dish_id
"""

_MICRO_REF_SQL = """
SELECT
    nr.nutrient_id,
    n.name_zh AS nutrient_name,
    n.unit,
    nr.reference_type,
    nr.value AS reference_value,
    nr.ul_value,
    nr.sex,
    nr.age_group,
    nr.life_stage,
    nr.menstrual_status
FROM core.nutrient_reference nr
JOIN core.nutrient n ON n.nutrient_id = nr.nutrient_id
WHERE nr.nutrient_id = ANY(:nutrient_ids)
  AND nr.sex = ANY(:sex_values)
  AND nr.life_stage = '普通'
  AND nr.menstrual_status = ''
  AND nr.age_min_months <= :age_months
  AND (nr.age_max_months IS NULL OR nr.age_max_months >= :age_months)
ORDER BY nr.nutrient_id, nr.reference_type
"""


class SqlDataSource:
    """从 diet_agent 库读取事实数据（同步 Session）。"""

    def __init__(self, session: Any) -> None:
        self.session = session

    def get_goal_row(self, goal_code: str) -> dict[str, Any] | None:
        from sqlalchemy import text

        row = (
            self.session.execute(
                text(
                    """
                    SELECT goal_code, goal_name, macro_policy, oil_salt_sugar_policy,
                           ingredient_method_policy, activity_factor, energy_policy, version
                    FROM core.goal_structure_map
                    WHERE goal_code = :code AND is_active
                    LIMIT 1
                    """
                ),
                {"code": goal_code},
            )
            .mappings()
            .first()
        )
        return dict(row) if row else None

    def get_micro_reference_rows(self, profile: Profile) -> list[dict[str, Any]]:
        from sqlalchemy import text

        sex_values = SEX_VARIANTS.get(profile.gender.strip(), [profile.gender, "both"])
        rows = (
            self.session.execute(
                text(_MICRO_REF_SQL),
                {
                    "nutrient_ids": list(MICRO_IDS),
                    "sex_values": sex_values,
                    "age_months": int(profile.age) * 12,
                },
            )
            .mappings()
            .all()
        )
        return [dict(r) for r in rows]

    def get_dish_facts(self) -> list[DishFacts]:
        from sqlalchemy import text

        rows = self.session.execute(text(_DISH_SQL)).mappings().all()
        out: list[DishFacts] = []
        for row in rows:
            data = dict(row)
            out.append(
                DishFacts(
                    dish_id=str(data["dish_id"]),
                    name=str(data["name"]),
                    category=data.get("category"),
                    tags=list(data.get("tags") or []),
                    method_text=data.get("method_text"),
                    cooking_rule_id=data.get("cooking_rule_id"),
                    servings=float(data.get("servings") or 1.0),
                    default_oil_g=_to_float(data.get("default_oil_g")),
                    default_salt_g=_to_float(data.get("default_salt_g")),
                    cook_time_min=data.get("cook_time_min"),
                    energy_kcal=_to_float(data.get("energy_kcal")),
                    protein_g=_to_float(data.get("protein_g")),
                    fat_g=_to_float(data.get("fat_g")),
                    carb_g=_to_float(data.get("carb_g")),
                    fiber_g=_to_float(data.get("fiber_g")),
                    sodium_mg=_to_float(data.get("sodium_mg")),
                    calcium_mg=_to_float(data.get("calcium_mg")),
                    micro={
                        "calcium": _to_float(data.get("calcium_mg")),
                        "iron": _to_float(data.get("iron")),
                        "zinc": _to_float(data.get("zinc")),
                        "vitamin_a": _to_float(data.get("vitamin_a")),
                        "vitamin_b1": _to_float(data.get("vitamin_b1")),
                        "vitamin_b2": _to_float(data.get("vitamin_b2")),
                        "vitamin_c": _to_float(data.get("vitamin_c")),
                    },
                    strict_allergens=list(data.get("strict_allergens") or []),
                    unverified_food_ids=list(data.get("unverified_food_ids") or []),
                    ingredient_names=list(data.get("ingredient_names") or []),
                    source=data.get("source"),
                )
            )
        return out

    def get_micro_window(
        self, user_id: str, window_start: str, window_end: str
    ) -> list[dict[str, Any]]:
        from sqlalchemy import text

        rows = (
            self.session.execute(
                text(
                    "SELECT nutrient_id, nutrient_name, unit, total_value, "
                    "selected_meal_count, known_meal_count, missing_meal_count "
                    "FROM app.recent_micro_balance(:uid, CAST(:ws AS date), CAST(:we AS date))"
                ),
                {"uid": user_id, "ws": window_start, "we": window_end},
            )
            .mappings()
            .all()
        )
        return [dict(r) for r in rows]


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- 离线源（无库自测）


class CsvDishSource:
    """用 v1.2 交付包的《菜式数据明细_60道.csv》构造 DishFacts。

    只作为联调前的离线验证源：该 CSV 仅有 energy / protein / sodium / calcium，
    fat / carb / fiber / 7 微量一律为 None（保持缺失语义，便于验证「null≠0」逻辑）。
    """

    def __init__(self, csv_path: str) -> None:
        self.csv_path = csv_path

    def load(self) -> list[DishFacts]:
        out: list[DishFacts] = []
        with open(self.csv_path, encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                out.append(
                    DishFacts(
                        dish_id=row["dish_id"].strip(),
                        name=row["name"].strip(),
                        category=(row.get("category") or "").strip() or None,
                        tags=_parse_pg_array(row.get("tags")),
                        method_text=(row.get("method_text") or "").strip() or None,
                        cooking_rule_id=(row.get("cooking_rule_id") or "").strip() or None,
                        servings=float(row.get("servings") or 1.0),
                        default_oil_g=_to_float(row.get("default_oil_g")),
                        default_salt_g=_to_float(row.get("default_salt_g")),
                        cook_time_min=int(row["cook_time_min"]) if (row.get("cook_time_min") or "").strip() else None,
                        energy_kcal=_to_float(row.get("energy_kcal")),
                        protein_g=_to_float(row.get("protein_g")),
                        fat_g=None,
                        carb_g=None,
                        fiber_g=None,
                        sodium_mg=_to_float(row.get("sodium_mg")),
                        calcium_mg=_to_float(row.get("calcium_mg")),
                        micro={
                            "calcium": _to_float(row.get("calcium_mg")),
                            "iron": None,
                            "zinc": None,
                            "vitamin_a": None,
                            "vitamin_b1": None,
                            "vitamin_b2": None,
                            "vitamin_c": None,
                        },
                        strict_allergens=_parse_pg_array(row.get("strict_allergens")),
                        unverified_food_ids=_parse_pg_array(row.get("unverified_food_ids")),
                        ingredient_names=_parse_ingredient_text(row.get("ingredients")),
                        source=(row.get("source") or "").strip() or None,
                    )
                )
        return out


def _parse_pg_array(raw: str | None) -> list[str]:
    """解析 '{甲,乙}' 形式的 PostgreSQL 数组文本。"""
    if not raw:
        return []
    text = raw.strip()
    if text.startswith("{") and text.endswith("}"):
        text = text[1:-1]
    if not text:
        return []
    parts: list[str] = []
    for item in text.split(","):
        clean = item.strip().strip('"').strip()
        if clean:
            parts.append(clean)
    return parts


def _parse_ingredient_text(raw: str | None) -> list[str]:
    """从「鸡胸肉 150g（主料）；大蒜 5g（调味辅料）」抽取食材名。"""
    if not raw:
        return []
    names: list[str] = []
    for chunk in str(raw).replace("；", ";").split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        token = chunk.split("（")[0].strip()
        # 去掉重量部分：以空格或数字开头处截断
        name = ""
        for char in token:
            if char.isdigit() or char in {" ", "\t"}:
                break
            name += char
        if name:
            names.append(name)
    return names
