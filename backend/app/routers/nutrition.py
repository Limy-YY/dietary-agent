"""周度营养报告接口（T4+T5 / API-13）。

流程：用户档案 → age_in_months → match_nutrient_reference（RNI/AI/UL 对照）
→ 周摄入（app.nutrition_result）→ evaluate_weekly_ul（UL 超限评估）。
注意：core.nutrient_reference.sex 存储为 female/male/both，需将档案中的
中文性别（女/男）映射后再调用。
"""
import json
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import BizCode, BizError
from app.core.response import ApiResponse, api_success
from app.db import get_db
from app.schemas.nutrition import ReferenceItem, UlAssessmentItem, WeeklyReport

router = APIRouter(prefix="/nutrition", tags=["nutrition"])

_SEX_MAP = {
    "女": "female", "female": "female", "f": "female", "F": "female",
    "男": "male", "male": "male", "m": "male", "M": "male",
    "both": "both",
}


def _normalize_sex(raw: str | None) -> str | None:
    if not raw:
        return None
    return _SEX_MAP.get(raw.strip().lower())


def _to_float(v):
    return float(v) if v is not None else None


@router.get("/weekly-report")
def weekly_report(
    user_id: str = Query(...),
    week_start: date = Query(...),
    db: Session = Depends(get_db),
) -> ApiResponse[WeeklyReport]:
    """获取周度微量营养素评估报告（参考值对照 + UL 超限评估）。"""
    notes: list[str] = []

    profile = db.execute(
        text(
            "SELECT user_id, sex, birth_date, extras FROM app.profile "
            "WHERE user_id = :uid"
        ),
        {"uid": user_id},
    ).mappings().first()
    if profile is None:
        raise BizError(code=BizCode.NOT_FOUND, message=f"用户档案不存在: {user_id}")

    extras = profile["extras"] if isinstance(profile["extras"], dict) else {}
    life_stage = extras.get("life_stage") or "普通"
    menstrual_status = extras.get("menstrual_status")

    age_months = None
    if profile["birth_date"]:
        age_months = db.execute(
            text("SELECT app.age_in_months(:bd)"), {"bd": profile["birth_date"]}
        ).scalar_one()

    sex_en = _normalize_sex(profile["sex"])
    if sex_en is None:
        sex_en = "both"
        notes.append("档案性别缺失或无法识别，参考值按 both 口径返回，建议完善档案")

    # T4：参考值匹配
    refs = db.execute(
        text(
            "SELECT * FROM app.match_nutrient_reference(:sex, :age_months, :life_stage, :ms)"
        ),
        {"sex": sex_en, "age_months": age_months, "life_stage": life_stage, "ms": menstrual_status},
    ).mappings().all()
    references = [
        ReferenceItem(
            nutrient_id=r["nutrient_id"],
            nutrient_name=r["nutrient_name"],
            unit=r["unit"],
            reference_type=r["reference_type"],
            reference_value=_to_float(r["reference_value"]),
            ul_value=_to_float(r["ul_value"]),
            sex=r["sex"],
            age_group=r["age_group"],
            life_stage=r["life_stage"],
            menstrual_status=r["menstrual_status"],
            needs_clarification=r["needs_clarification"],
        )
        for r in refs
    ]
    if any(r.needs_clarification for r in references):
        notes.append("部分营养素存在多组参考值（needs_clarification），需向用户确认，不得自行取值")

    # 周摄入：nutrition_result（表结构含 computed jsonb；联调期按数据岗口径解析）
    week_end = week_start + timedelta(days=7)
    intake_rows = db.execute(
        text(
            "SELECT target_id, amount_g, method, computed, sources, created_at "
            "FROM app.nutrition_result "
            "WHERE user_id = :uid AND created_at >= :ws AND created_at < :we "
            "ORDER BY created_at"
        ),
        {"uid": user_id, "ws": week_start, "we": week_end},
    ).mappings().all()
    intake_records = [dict(r) for r in intake_rows]
    if not intake_records:
        notes.append("本周无摄入记录，UL 评估返回空，days_recorded=0（数据不足，勿作达标/超标结论）")

    # T5：UL 评估（daily_intakes 为 jsonb 数组 [{date, nutrient_id, amount}, ...]，
    # 结构以 T11 /calc/nutrition 输出对齐；当前无记录传空数组）
    daily_intakes: list = []
    for r in intake_rows:
        computed = r["computed"]
        # computed 结构待数据岗确认（D 项），当前不猜测解析，仅返回原始记录
        if isinstance(computed, list):
            daily_intakes.extend(computed)
    if not daily_intakes:
        daily_intakes = []

    ul_rows = db.execute(
        text(
            "SELECT * FROM app.evaluate_weekly_ul(cast(:intakes AS jsonb), :sex, :age_months, :life_stage, :ms)"
        ),
        {
            "intakes": json.dumps(daily_intakes),
            "sex": sex_en,
            "age_months": age_months,
            "life_stage": life_stage,
            "ms": menstrual_status,
        },
    ).mappings().all()
    ul_assessment = [
        UlAssessmentItem(
            nutrient_id=r["nutrient_id"],
            nutrient_name=r["nutrient_name"],
            unit=r["unit"],
            days_recorded=r["days_recorded"],
            weekly_total=_to_float(r["weekly_total"]),
            daily_average=_to_float(r["daily_average"]),
            daily_max=_to_float(r["daily_max"]),
            ul_value=_to_float(r["ul_value"]),
            days_over_ul=r["days_over_ul"],
            evaluation_status=r["evaluation_status"],
        )
        for r in ul_rows
    ]

    return api_success(
        WeeklyReport(
            user_id=user_id,
            week_start=str(week_start),
            age_months=age_months,
            sex=profile["sex"],
            references=references,
            ul_assessment=ul_assessment,
            intake_records=intake_records,
            notes=notes,
        )
    )
