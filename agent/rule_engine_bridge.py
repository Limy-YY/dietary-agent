# -*- coding: utf-8 -*-
"""规则引擎桥接：进程内直调后端 rule_engine 的 generate_plan。

后端 rule_engine 是纯计算五步算法（不写库、不走 HTTP），本模块负责：
1. import 后端的 app.services.rule_engine；
2. 把后端档案（app.profile 扁平字段）映射成 rule_engine 的 Profile / PlanRequest；
3. 调 generate_plan，并把结果转成前端契约里的 `plan` 对象（供 blocks.py 组装卡片）。
"""
from __future__ import annotations

import sys
from datetime import date, timedelta

# 把后端目录加入 sys.path，以便 import app.services.rule_engine
import config

if config.BACKEND_DIR not in sys.path:
    sys.path.insert(0, config.BACKEND_DIR)

from app.services.rule_engine import (  # noqa: E402
    PlanRequest,
    Profile,
    SqlDataSource,
    generate_plan,
)
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

# ---------------------------------------------------------------- 常量映射

# 档案 goal（中文或英文码）→ rule_engine 的 goal_code
GOAL_MAP = {
    "维持": "maintain", "maintain": "maintain",
    "减脂": "fat_loss", "fat_loss": "fat_loss", "cut": "fat_loss",
    "增肌": "muscle_gain", "muscle_gain": "muscle_gain",
    "增重": "muscle_gain", "bulk": "muscle_gain",
    "控糖": "glucose_control", "glucose_control": "glucose_control",
    "改善肠胃": "digestive_health", "digestive_health": "digestive_health",
}

# rule_engine 餐次（早/午/晚）→ 前端 meal_type
MEAL_TYPE_MAP = {"早": "breakfast", "午": "lunch", "晚": "dinner"}
MEAL_LABEL = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐"}
MEAL_TIME = {"breakfast": "07:30", "lunch": "12:00", "dinner": "18:30"}
MEAL_COLOR = {"breakfast": "#e8942c", "lunch": "#4a7c59", "dinner": "#3b7fd4"}
MEAL_ORDER = {"早": 1, "午": 2, "晚": 3}

WEEKDAY_ZH = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# 宗教/伦理忌口关键词（命中则归入 religious_ethical，否则当作排除食材）
RELIGIOUS_LABELS = {"清真", "伊斯兰", "素食", "佛教", "回民"}

_engine = None
_SessionLocal = None


def _get_session():
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_engine(config.DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=10)
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _SessionLocal()


# ---------------------------------------------------------------- 档案 / 请求构造

def build_profile(profile: dict) -> Profile:
    """后端 app.profile（扁平）→ rule_engine Profile。"""
    extras = profile.get("extras") or {}
    allergies = [a for a in (profile.get("allergies") or []) if a and a != "无"]
    taboos = [t for t in (profile.get("taboos") or []) if t and t != "无"]

    religious = [t for t in taboos if t in RELIGIOUS_LABELS]
    exclude = [t for t in taboos if t not in RELIGIOUS_LABELS]

    # 后端 conditions 是中文病名列表；rule_engine 用 dict{id: {status}}。
    # 当前 pipeline 仅把 confirmed 病名写进说明、不参与过滤，故直接按病名作 key。
    conditions = {c: {"status": "confirmed"} for c in (profile.get("conditions") or []) if c}

    return Profile(
        gender=profile.get("sex") or "女",
        age=int(profile.get("age") or 20),
        height_cm=float(profile.get("height_cm") or 160),
        weight_kg=float(profile.get("weight_kg") or 55),
        goal_code=GOAL_MAP.get(str(profile.get("goal") or "maintain"), "maintain"),
        conditions=conditions,
        allergies=allergies,
        religious_ethical=religious,
        cooking_equipment=list(extras.get("cookware") or []),
        name=extras.get("name"),
    )


def build_request(user_id: str, profile: dict, params: dict) -> PlanRequest:
    """意图参数 → PlanRequest。params: {scope, meal_type, start_date?, end_date?}。"""
    scope = params.get("scope", "day")
    today = date.today()

    if scope == "week":
        start = params.get("start_date") or today.isoformat()
        start_d = date.fromisoformat(start)
        end_d = start_d + timedelta(days=6)
        plan_type = "周"
        meal_types = ["早", "午", "晚"]
    elif scope == "meal":
        meal_type = params.get("meal_type") or "午"
        start = end = (params.get("start_date") or today.isoformat())
        plan_type = "日"
        meal_types = [meal_type]
    else:  # day
        start = end = (params.get("start_date") or today.isoformat())
        plan_type = "日"
        meal_types = ["早", "午", "晚"]

    # 忌口里的非宗教项 → 硬排除食材
    extras = profile.get("extras") or {}
    taboos = [t for t in (profile.get("taboos") or []) if t and t != "无"]
    exclude = [t for t in taboos if t not in RELIGIOUS_LABELS]

    return PlanRequest(
        start_date=start,
        end_date=end,
        plan_type=plan_type,
        meal_types=meal_types,
        candidates_per_slot=params.get("candidates_per_slot", 3),
        user_id=user_id,
        exclude_ingredients=exclude,
        window_days=params.get("window_days", 7),
    )


# ---------------------------------------------------------------- 结果 → plan 字典

def _weekday_zh(iso: str) -> str:
    d = date.fromisoformat(iso)
    return WEEKDAY_ZH[d.weekday()]


def _md(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.month:02d}-{d.day:02d}"


def _portion_text(servings: float) -> str:
    if servings == 1:
        return "1 份"
    if servings == 0.5:
        return "半份"
    if servings > 1:
        return f"{servings:g} 份"
    return ""


def _dish_list(candidate) -> list[dict]:
    """候选 → 前端 dishes（含每道菜估量 kcal，来自 facts 能量 × 份量）。"""
    dishes = []
    for p in candidate.portions:
        kcal = p.scaled(p.facts.energy_kcal) if p.facts.energy_kcal is not None else None
        dishes.append({
            "name": p.name,
            "amount": _portion_text(p.servings),
            "kcal": round(kcal, 1) if kcal is not None else 0,
            "tip": "",
            "is_staple": bool(p.facts.is_staple),
        })
    return dishes


def _candidate_view(candidate, rank: int) -> dict:
    names = [p.name for p in candidate.portions]
    letter = chr(ord("A") + max(0, rank - 1)) if 0 < rank <= 3 else str(rank)
    return {
        "candidate_id": str(candidate.candidate_id),
        "name": f"方案 {letter} · {' + '.join(names)}",
        "kcal": round(candidate.totals.get("kcal") or 0, 1),
        "desc": candidate.why_text or candidate.eating_order_advice or "",
        "dishes": _dish_list(candidate),
    }


def _slot_view(slot, day_index: int) -> dict:
    meal_type = MEAL_TYPE_MAP.get(slot.meal_type, "lunch")
    picked = None
    for c in slot.candidates:
        if str(c.candidate_id) == str(slot.selected_candidate_id):
            picked = c
            break
    if picked is None and slot.candidates:
        picked = slot.candidates[0]

    dishes = _dish_list(picked) if picked else []
    return {
        "slot_id": f"s-{day_index}-{meal_type}",
        "meal_type": meal_type,
        "label": MEAL_LABEL[meal_type],
        "time": MEAL_TIME[meal_type],
        "color": MEAL_COLOR[meal_type],
        "kcal": round(picked.totals.get("kcal") or 0, 1) if picked else 0,
        "oil_g": round(picked.oil_salt.get("oil_g") or 0, 1) if picked else 0,
        "salt_g": round(picked.oil_salt.get("salt_g") or 0, 1) if picked else 0,
        "dish_text": " + ".join(p.name for p in picked.portions) if picked else "",
        "dish_count": len(dishes),
        "dishes": dishes,
        "candidates": [_candidate_view(c, c.rank) for c in slot.candidates],
        "selected_candidate_id": str(slot.selected_candidate_id) if slot.selected_candidate_id is not None else "",
        "micro": [],
    }


def _macro_segments(result, day_slots: list) -> list[dict]:
    """把当日选中候选的宏量合计换算成占比，与目标占比对比给 tag。"""
    kcal = protein = fat = carb = 0.0
    for slot in day_slots:
        for c in slot.candidates:
            if str(c.candidate_id) == str(slot.selected_candidate_id):
                t = c.totals
                kcal += t.get("kcal") or 0
                protein += t.get("protein_g") or 0
                fat += t.get("fat_g") or 0
                carb += t.get("carb_g") or 0
                break
    if kcal <= 0:
        kcal = result.targets.energy_kcal or 0
    p_pct = round(protein * 4 / kcal * 100) if kcal else 0
    f_pct = round(fat * 9 / kcal * 100) if kcal else 0
    c_pct = round(carb * 4 / kcal * 100) if kcal else 0

    policy = result.targets.goal_policy
    target_g = {
        "protein_g": kcal * policy.protein_pct / 4,
        "fat_g": kcal * policy.fat_pct / 9,
        "carb_g": kcal * policy.carb_pct / 4,
    }

    def seg(name, pct, color, grams, target, tgt_pct):
        if target and target > 0:
            ok = abs(grams - target) / target <= 0.2
            tag, level = ("达标", "ok") if ok else ("注意", "warn")
        else:
            tag, level = "目标", "blue"
        return {
            "name": name, "percent": pct, "color": color, "tag": tag, "tag_level": level,
            "desc": f"约 {round(grams)}g / 目标 {round(target)}g（{round(tgt_pct*100)}%）",
        }

    return [
        seg("蛋白质", p_pct, "protein", protein, target_g["protein_g"], policy.protein_pct),
        seg("碳水", c_pct, "carb", carb, target_g["carb_g"], policy.carb_pct),
        seg("脂肪", f_pct, "fat", fat, target_g["fat_g"], policy.fat_pct),
    ]


def _micro_items(result) -> list[dict]:
    """7 关键微量：有跨日平衡结果就映射覆盖度，否则给「参考提示」。"""
    if result.balance and result.balance.items:
        items = []
        for nid, m in result.balance.items.items():
            pct = round(m.covered_pct or 0)
            status = "ok" if pct >= 80 else "warn" if pct >= 50 else "danger"
            items.append({
                "name": m.name_zh,
                "value": f"{pct}%",
                "ring_percent": pct,
                "status": status,
                "note": m.note or f"目标 {round(m.target) if m.target is not None else '—'} {m.unit}",
            })
        return items
    # 无摄入记录时保持 null≠0 语义：只作参考提示
    return [
        {"name": zh, "value": "—", "ring_percent": 0, "status": "ok", "note": "暂无摄入记录，仅作参考提示"}
        for _, zh, _ in [
            ("calcium", "钙", "mg"), ("iron", "铁", "mg"), ("zinc", "锌", "mg"),
            ("vitamin_a", "维生素A", "μgRAE"), ("vitamin_b1", "维生素B1", "mg"),
            ("vitamin_b2", "维生素B2", "mg"), ("vitamin_c", "维生素C", "mg"),
        ]
    ]


def _result_to_plan(result, profile: dict) -> dict:
    """rule_engine PlanResult → 前端契约里的 plan 对象。"""
    scope = {"日": "day", "周": "week"}.get(result.plan_type, "day")
    if len(result.slots) and len({s.meal_type for s in result.slots}) == 1:
        scope = "meal"

    today = date.today()
    days: list[dict] = []
    by_date: dict[str, list] = {}
    for s in result.slots:
        by_date.setdefault(s.slot_date, []).append(s)
    # 按日期自然序
    for iso in sorted(by_date.keys()):
        slots = sorted(by_date[iso], key=lambda x: MEAL_ORDER.get(x.meal_type, 9))
        day_kcal = 0.0
        for s in slots:
            for c in s.candidates:
                if str(c.candidate_id) == str(s.selected_candidate_id):
                    day_kcal += c.totals.get("kcal") or 0
                    break
        days.append({
            "date": _md(iso),
            "iso": iso,
            "weekday": _weekday_zh(iso),
            "is_today": date.fromisoformat(iso) == today,
            "kcal": round(day_kcal, 1),
            "slots": [_slot_view(s, len(days)) for s in slots],
        })

    first = days[0] if days else None
    energy = round(result.targets.energy_kcal, 1)
    goal_name = result.targets.goal_name or str(profile.get("goal") or "维持")
    title = {"week": "接下来七天食谱", "meal": "午餐搭配", "day": "今日三餐"}.get(scope, "今日三餐")
    subtitle = (
        f"目标：{goal_name} · {result.start_date} ~ {result.end_date} · 日均约 {energy} kcal"
        if scope == "week"
        else f"目标：{goal_name} · 全天约 {energy} kcal"
    )
    range_text = f"{_md(result.start_date)} ~ {_md(result.end_date)}" if scope == "week" else (
        f"{_md(result.start_date)} {_weekday_zh(result.start_date)}"
    )

    macro_segments = _macro_segments(result, by_date.get(sorted(by_date.keys())[0], []) if by_date else [])
    nutrition = {
        "scope": scope,
        "macro": {"center_value": str(round(energy)), "center_label": "kcal 全天", "segments": macro_segments},
        "micro": {"title": "关键微量元素覆盖", "items": _micro_items(result)},
        "insights": (result.reference_hints or [])[:3],
        "coverage": {"level": "ok", "text": "7 项关键微量按跨日动态平衡评估"},
    }

    reason_points = [result.why_summary] if result.why_summary else []
    reason_points += (result.data_quality_notes or [])[:2]

    return {
        "plan_id": f"plan_{date.today():%Y%m%d}_{len(days) or 1}d",
        "plan_type": scope,
        "status": "candidates" if result.status == "candidates" else "draft",
        "title": title,
        "subtitle": subtitle,
        "range_text": range_text,
        "plan_date": first["iso"] if first else today.isoformat(),
        "goal_energy_kcal": energy,
        "goal_text": f"{goal_name} · 目标 {energy} kcal",
        "macro_ratio": {k: v.ratio for k, v in result.targets.meal_targets.items()},
        "days": days,
        "nutrition": nutrition,
        "reason_points": reason_points,
        "updated_at": date.today().isoformat(),
        "executed": False,
    }


# ---------------------------------------------------------------- 对外入口

def generate_plan_dict(user_id: str, profile: dict, params: dict) -> dict:
    """生成方案并转成前端 plan 字典。失败抛 RuleEngineError / BackendError 语义异常。"""
    rp = build_profile(profile)
    req = build_request(user_id, profile, params)
    session = _get_session()
    try:
        result = generate_plan(rp, req, SqlDataSource(session))
    finally:
        session.close()
    return _result_to_plan(result, profile)
