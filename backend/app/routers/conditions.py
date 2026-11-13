"""疾病规则接口（T6/T7/T8 / API-17/18/19）。

语义约定：
- 目录（catalog）含待审核规则，仅 production_ready=true 可用于正式判断；
  当前正式规则为 0 条 = 未审核启用，不是"无规则"。
- 评估（evaluate）只按生产函数执行；missing_value_count>0 时不得断言达标/超标。
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.response import ApiResponse, PageData, api_success, page_data
from app.db import get_db
from app.schemas.conditions import EvaluateRuleRequest, EvaluateRuleResult, RuleItem

router = APIRouter(prefix="/condition-rules", tags=["condition-rules"])

_CATALOG_COLS = (
    "rule_id, condition_id, condition_name_zh, rule_name_zh, rule_kind, nutrient_id, "
    "nutrient_name_zh, action, comparator, target_value, target_unit, time_basis, "
    "population, selector, message_zh, safety_note_zh, review_status, "
    "medical_review_required, is_active, production_ready, sources"
)
# 生产视图不含审核状态列（v_production_condition_rules 为已启用规则的内容视图）
_PROD_COLS = (
    "rule_id, condition_id, condition_name_zh, rule_name_zh, rule_kind, nutrient_id, "
    "nutrient_name_zh, action, comparator, target_value, target_unit, time_basis, "
    "population, selector, message_zh, safety_note_zh, sources"
)


def _rule_item(row) -> RuleItem:
    return RuleItem(**{k: row[k] for k in row.keys()})


@router.get("/catalog")
def rule_catalog(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[RuleItem]]:
    """查看疾病规则目录（含待审核规则与来源，T6）。"""
    total = db.execute(
        text("SELECT count(*) FROM app.v_condition_rule_catalog")
    ).scalar_one()
    offset = (page - 1) * page_size
    rows = db.execute(
        text(
            f"SELECT {_CATALOG_COLS} FROM app.v_condition_rule_catalog "
            f"ORDER BY condition_id, rule_id LIMIT :limit OFFSET :offset"
        ),
        {"limit": page_size, "offset": offset},
    ).mappings().all()
    items = [_rule_item(r) for r in rows]
    return api_success(page_data(items, total=total, page=page, page_size=page_size))


@router.get("/production")
def production_rules(db: Session = Depends(get_db)) -> ApiResponse[list[RuleItem]]:
    """查询正式疾病规则（仅 production_ready=true，当前 0 条，T7）。"""
    rows = db.execute(
        text(f"SELECT {_PROD_COLS} FROM app.v_production_condition_rules ORDER BY condition_id, rule_id")
    ).mappings().all()
    return api_success([_rule_item(r) for r in rows])


@router.post("/evaluate")
def evaluate_rule(
    req: EvaluateRuleRequest, db: Session = Depends(get_db)
) -> ApiResponse[EvaluateRuleResult]:
    """执行疾病规则评估（T8，生产函数）。

    生产函数仅评估 approved+active 规则；规则存在但未审核启用时返回非正式状态，
    不得作正式判断；规则不存在时返回 1004。
    """
    from app.core.errors import BizCode, BizError

    rows = db.execute(
        text(
            "SELECT * FROM app.evaluate_daily_condition_nutrient_rule(:uid, :d, :rid)"
        ),
        {"uid": req.user_id, "d": req.intake_date, "rid": req.rule_id},
    ).mappings().all()
    if rows:
        r = rows[0]
        return api_success(
            EvaluateRuleResult(
                user_id=r["user_id"],
                intake_date=str(r["intake_date"]),
                rule_id=r["rule_id"],
                condition_id=r["condition_id"],
                condition_status=r["condition_status"],
                review_status=r["review_status"],
                production_ready=r["production_ready"],
                comparator=r["comparator"],
                applied_target=float(r["applied_target"]) if r["applied_target"] is not None else None,
                target_unit=r["target_unit"],
                known_total=float(r["known_total"]) if r["known_total"] is not None else None,
                record_count=r["record_count"],
                missing_value_count=r["missing_value_count"],
                full_day_scope=r["full_day_scope"],
                evaluation_status=r["evaluation_status"],
                explanation_zh=r["explanation_zh"],
            )
        )

    # 规则存在但未审核启用 → 返回非正式状态（不得作正式判断）
    rule = db.execute(
        text(
            f"SELECT {_CATALOG_COLS} FROM app.v_condition_rule_catalog WHERE rule_id = :rid"
        ),
        {"rid": req.rule_id},
    ).mappings().first()
    if rule is not None:
        return api_success(
            EvaluateRuleResult(
                user_id=req.user_id,
                intake_date=str(req.intake_date),
                rule_id=rule["rule_id"],
                condition_id=rule["condition_id"],
                condition_status=None,
                review_status=rule["review_status"],
                production_ready=False,
                comparator=rule["comparator"],
                applied_target=float(rule["target_value"]) if rule["target_value"] is not None else None,
                target_unit=rule["target_unit"],
                known_total=None,
                record_count=0,
                missing_value_count=0,
                full_day_scope=False,
                evaluation_status="rule_not_approved",
                explanation_zh=(
                    f"规则「{rule['rule_name_zh']}」未审核启用（{rule['review_status']}），"
                    "不得作正式达标/超标判断；需先由数据岗/医学审核后启用"
                ),
            )
        )

    raise BizError(code=BizCode.NOT_FOUND, message=f"规则不存在: {req.rule_id}")
