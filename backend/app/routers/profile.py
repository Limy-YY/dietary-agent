"""用户档案接口（API-01 / API-02）。

写：`app.profile`（v1.2 十一项 + 后端算 `target_calories`，同步兼容列 `sex`）；
读：`app.v_profile_effective`（`COALESCE(gender, sex)` / `COALESCE(goal_code, goal)`），
并 join `core.goal_structure_map` 取中文 `goal_name`。

v1.1 兼容列约定（契约 §3.3）：`sex` 随 `gender` 同步供库函数使用；
`goal / taboos / activity_level / birth_date / extras` 只读，新接口不写入。
"""
import json

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import BizCode, BizError
from app.core.response import ApiResponse, api_success
from app.core.security import CurrentUser
from app.db import get_db
from app.schemas.profile import ProfileUpsertRequest, UserProfile

router = APIRouter(prefix="/profile", tags=["profile"])

# 视图已做旧列回退（gender/goal_code）；`sex / goal / taboos` 等兼容列仍需回原表取
PROFILE_SQL = """
SELECT p.user_id, p.name, p.avatar, p.gender, p.age, p.height_cm, p.weight_kg,
       p.goal_code, p.cooking_equipment, p.conditions, p.allergies, p.religious_ethical,
       p.target_calories, p.profile_version,
       p.taboos, p.birth_date, p.created_at, p.updated_at,
       p.gender_from_legacy, p.goal_code_from_legacy,
       raw.sex, raw.goal,
       g.goal_name
FROM app.v_profile_effective p
LEFT JOIN app.profile raw ON raw.user_id = p.user_id
LEFT JOIN core.goal_structure_map g ON g.goal_code = p.goal_code
WHERE p.user_id = :uid
"""

_ALLOWED_STATUS = ("confirmed", "suspected", "unknown")


def _f(v):
    return float(v) if v is not None else None


def row_to_profile(row) -> UserProfile:
    """把 `PROFILE_SQL` 的一行映射成出参；缺列时按 None 处理，便于他处复用。"""
    keys = row.keys()

    def g(key):
        return row[key] if key in keys else None

    cond = g("conditions")
    birth = g("birth_date")
    created = g("created_at")
    updated = g("updated_at")
    return UserProfile(
        user_id=row["user_id"],
        name=g("name"),
        avatar=g("avatar"),
        gender=g("gender"),
        age=g("age"),
        height_cm=_f(g("height_cm")),
        weight_kg=_f(g("weight_kg")),
        goal_code=g("goal_code"),
        goal_name=g("goal_name"),
        cooking_equipment=list(g("cooking_equipment") or []),
        conditions=cond if isinstance(cond, dict) else {},
        allergies=list(g("allergies") or []),
        religious_ethical=list(g("religious_ethical") or []),
        target_calories=_f(g("target_calories")),
        profile_version=g("profile_version"),
        sex=g("sex"),
        goal=g("goal"),
        taboos=list(g("taboos") or []),
        birth_date=str(birth) if birth else None,
        created_at=created.isoformat() if hasattr(created, "isoformat") else created,
        updated_at=updated.isoformat() if hasattr(updated, "isoformat") else updated,
        gender_from_legacy=bool(g("gender_from_legacy")),
        goal_code_from_legacy=bool(g("goal_code_from_legacy")),
    )


def _bmr_kcal(gender: str, age: float, height_cm: float, weight_kg: float) -> float:
    """Mifflin-St Jeor 基础代谢。"""
    base = 10.0 * weight_kg + 6.25 * height_cm - 5.0 * age
    if gender == "男":
        return base + 5.0
    if gender == "女":
        return base - 161.0
    raise BizError(BizCode.CALC_FAILED, f"BMR 计算失败：未知性别 {gender}", http_status=400)


def _target_calories(gender: str, age: int, height_cm: float, weight_kg: float) -> float:
    """`target_calories = BMR × 1.4`（v1.2 统一活动系数，已删除 activity_level）。"""
    try:
        bmr = _bmr_kcal(gender, age, height_cm, weight_kg)
        target = round(bmr * 1.4, 1)
    except BizError:
        raise
    except Exception as exc:  # noqa: BLE001 - 统一映射为 2001
        raise BizError(BizCode.CALC_FAILED, f"BMR 计算失败：{exc}", http_status=400) from exc
    if target <= 0:
        raise BizError(
            BizCode.CALC_FAILED,
            f"BMR 计算结果非正（{target}），请核对身高体重",
            http_status=400,
        )
    return target


def _check_goal_code(db: Session, goal_code: str) -> str:
    row = db.execute(
        text(
            "SELECT goal_code FROM core.goal_structure_map "
            "WHERE goal_code = :g AND is_active"
        ),
        {"g": goal_code},
    ).first()
    if row is None:
        raise BizError(
            BizCode.PARAM_ERROR,
            f"goal_code 不在 goal_structure_map 中: {goal_code}"
            "（可选 maintain/fat_loss/muscle_gain/glucose_control/digestive_health）",
            http_status=400,
        )
    return goal_code


def _check_conditions(db: Session, conditions: dict[str, dict]) -> None:
    """三态结构校验：key 必须是 `core.health_condition.condition_id`，value 必须带合法 status。"""
    if not conditions:
        return
    for cid, detail in conditions.items():
        if not isinstance(detail, dict):
            raise BizError(
                BizCode.PARAM_ERROR,
                f"conditions.{cid} 必须是对象，如 {{\"status\":\"confirmed\"}}",
                http_status=400,
            )
        status = detail.get("status")
        if status not in _ALLOWED_STATUS:
            raise BizError(
                BizCode.PARAM_ERROR,
                f"conditions.{cid}.status 必须是 {'/'.join(_ALLOWED_STATUS)}",
                http_status=400,
            )

    known = set(
        db.execute(
            text(
                "SELECT condition_id FROM core.health_condition "
                "WHERE condition_id = ANY(CAST(:ids AS text[]))"
            ),
            {"ids": list(conditions)},
        ).scalars()
    )
    unknown = [c for c in conditions if c not in known]
    if unknown:
        raise BizError(
            BizCode.PARAM_ERROR,
            f"未知 condition_id: {', '.join(unknown)}（取 core.health_condition.condition_id）",
            http_status=400,
        )


def _upsert(req: ProfileUpsertRequest, user_id: str, db: Session) -> UserProfile:
    goal_code = _check_goal_code(db, req.goal_code)
    _check_conditions(db, req.conditions)
    target = _target_calories(req.gender, req.age, req.height_cm, req.weight_kg)

    db.execute(
        text(
            "INSERT INTO app.profile "
            "(user_id, name, avatar, gender, sex, age, height_cm, weight_kg, "
            " goal_code, cooking_equipment, conditions, allergies, religious_ethical, "
            " target_calories) "
            "VALUES (:uid, :name, :avatar, :gender, :sex, :age, :height, :weight, "
            "        :goal_code, :equipment, CAST(:conditions AS jsonb), :allergies, "
            "        :religious, :target) "
            "ON CONFLICT (user_id) DO UPDATE SET "
            " name = EXCLUDED.name, avatar = EXCLUDED.avatar, "
            " gender = EXCLUDED.gender, sex = EXCLUDED.sex, "
            " age = EXCLUDED.age, height_cm = EXCLUDED.height_cm, "
            " weight_kg = EXCLUDED.weight_kg, goal_code = EXCLUDED.goal_code, "
            " cooking_equipment = EXCLUDED.cooking_equipment, "
            " conditions = EXCLUDED.conditions, allergies = EXCLUDED.allergies, "
            " religious_ethical = EXCLUDED.religious_ethical, "
            " target_calories = EXCLUDED.target_calories, "
            " profile_version = app.profile.profile_version + 1, "
            " updated_at = now()"
        ),
        {
            "uid": user_id,
            "name": req.name,
            "avatar": req.avatar,
            "gender": req.gender,
            "sex": req.gender,  # 兼容列同步，供 match_nutrient_reference 等库函数使用
            "age": req.age,
            "height": req.height_cm,
            "weight": req.weight_kg,
            "goal_code": goal_code,
            "equipment": req.cooking_equipment,
            "conditions": json.dumps(req.conditions, ensure_ascii=False),
            "allergies": req.allergies,
            "religious": req.religious_ethical,
            "target": target,
        },
    )
    db.commit()

    row = db.execute(text(PROFILE_SQL), {"uid": user_id}).mappings().first()
    if row is None:
        raise BizError(BizCode.NOT_FOUND, "档案写入后未查到记录", http_status=404)
    return row_to_profile(row)


@router.put("")
def put_profile(
    req: ProfileUpsertRequest,
    user_id: str = CurrentUser,
    db: Session = Depends(get_db),
) -> ApiResponse[UserProfile]:
    """写档案（API-01，契约方法为 PUT）。"""
    return api_success(_upsert(req, user_id, db))


@router.post("")
def post_profile(
    req: ProfileUpsertRequest,
    user_id: str = CurrentUser,
    db: Session = Depends(get_db),
) -> ApiResponse[UserProfile]:
    """写档案（POST 别名，兼容既有调用方；语义与 PUT 一致）。"""
    return api_success(_upsert(req, user_id, db))


@router.get("")
def get_my_profile(
    user_id: str = CurrentUser,
    db: Session = Depends(get_db),
) -> ApiResponse[UserProfile]:
    """读当前登录用户档案（API-02）；未建档返回 404 / 1004。"""
    row = db.execute(text(PROFILE_SQL), {"uid": user_id}).mappings().first()
    if row is None:
        raise BizError(BizCode.NOT_FOUND, f"用户档案不存在: {user_id}", http_status=404)
    return api_success(row_to_profile(row))
