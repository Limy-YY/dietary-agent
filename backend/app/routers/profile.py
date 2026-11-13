"""用户档案接口（API-01/02）。

数据库对象：app.profile（业务表）。upsert 按 user_id 创建或更新。
"""
import json

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import BizCode, BizError
from app.core.response import ApiResponse, api_success
from app.db import get_db
from app.schemas.profile import ProfileUpsertRequest, UserProfile

router = APIRouter(prefix="/profile", tags=["profile"])

_COLS = (
    "user_id, sex, age, birth_date, height_cm, weight_kg, activity_level, goal, "
    "allergies, taboos, conditions, extras, created_at, updated_at"
)


def row_to_profile(row) -> UserProfile:
    extras = row["extras"] if isinstance(row["extras"], dict) else {}
    conditions = row["conditions"] if isinstance(row["conditions"], list) else []
    return UserProfile(
        user_id=row["user_id"],
        sex=row["sex"],
        age=row["age"],
        birth_date=str(row["birth_date"]) if row["birth_date"] else None,
        height_cm=float(row["height_cm"]) if row["height_cm"] is not None else None,
        weight_kg=float(row["weight_kg"]) if row["weight_kg"] is not None else None,
        activity_level=row["activity_level"],
        goal=row["goal"],
        allergies=list(row["allergies"] or []),
        taboos=list(row["taboos"] or []),
        conditions=conditions,
        menstrual_status=extras.get("menstrual_status") if isinstance(extras, dict) else None,
        extras=extras,
        created_at=str(row["created_at"]) if row["created_at"] else None,
        updated_at=str(row["updated_at"]) if row["updated_at"] else None,
    )


@router.post("")
def upsert_profile(
    req: ProfileUpsertRequest, db: Session = Depends(get_db)
) -> ApiResponse[UserProfile]:
    """创建 / 更新用户档案（API-01，按 user_id upsert）。"""
    db.execute(
        text(
            "INSERT INTO app.profile "
            "(user_id, sex, age, birth_date, height_cm, weight_kg, activity_level, goal, "
            " allergies, taboos, conditions, extras) "
            "VALUES (:uid, :sex, :age, :birth, :height, :weight, :activity, :goal, "
            "        :allergies, :taboos, cast(:conditions AS jsonb), cast(:extras AS jsonb)) "
            "ON CONFLICT (user_id) DO UPDATE SET "
            " sex = EXCLUDED.sex, age = EXCLUDED.age, birth_date = EXCLUDED.birth_date, "
            " height_cm = EXCLUDED.height_cm, weight_kg = EXCLUDED.weight_kg, "
            " activity_level = EXCLUDED.activity_level, goal = EXCLUDED.goal, "
            " allergies = EXCLUDED.allergies, taboos = EXCLUDED.taboos, "
            " conditions = EXCLUDED.conditions, extras = EXCLUDED.extras, "
            " updated_at = now()"
        ),
        {
            "uid": req.user_id,
            "sex": req.sex,
            "age": req.age,
            "birth": req.birth_date,
            "height": req.height_cm,
            "weight": req.weight_kg,
            "activity": req.activity_level,
            "goal": req.goal,
            "allergies": req.allergies,
            "taboos": req.taboos,
            "conditions": json.dumps(req.conditions),
            "extras": json.dumps(req.extras or {}),
        },
    )
    db.commit()
    row = db.execute(
        text(f"SELECT {_COLS} FROM app.profile WHERE user_id = :uid"),
        {"uid": req.user_id},
    ).mappings().first()
    return api_success(row_to_profile(row))


@router.get("/{user_id}")
def get_profile(user_id: str, db: Session = Depends(get_db)) -> ApiResponse[UserProfile]:
    """获取用户完整档案（API-02）。"""
    row = db.execute(
        text(f"SELECT {_COLS} FROM app.profile WHERE user_id = :uid"),
        {"uid": user_id},
    ).mappings().first()
    if row is None:
        raise BizError(code=BizCode.NOT_FOUND, message=f"用户档案不存在: {user_id}")
    return api_success(row_to_profile(row))
