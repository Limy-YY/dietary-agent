# -*- coding: utf-8 -*-
"""结构化边车（SSE meta.blocks）组装。

把 rule_engine 桥接出的 plan 字典 / 后端 REST 结果，转成前端契约里约定的 block。
字段对齐 frontend/docs/agent-output-contract.md，缺字段由前端 schema.js 兜底。
"""

SOURCES = [
    {"title": "中国居民膳食指南（2022）", "publisher": "中国营养学会",
     "published_at": "2022-04-26", "url": "http://dg.cnsoc.org/"},
    {"title": "中国食物成分表（标准版 第6版）", "publisher": "中国疾病预防控制中心营养与健康所",
     "published_at": "2018-08-01", "url": "https://www.chinanutri.cn/"},
    {"title": "中国居民膳食营养素参考摄入量（2023版）", "publisher": "中国营养学会",
     "published_at": "2023-09-01", "url": "https://www.cnsoc.org/"},
]


def _slot_view(slot: dict) -> dict:
    return {
        "slot_id": slot.get("slot_id", ""),
        "meal_type": slot.get("meal_type", "lunch"),
        "label": slot.get("label", ""),
        "time": slot.get("time", ""),
        "color": slot.get("color", ""),
        "kcal": slot.get("kcal", 0),
        "oil_g": slot.get("oil_g"),
        "salt_g": slot.get("salt_g"),
        "dish_text": slot.get("dish_text", ""),
        "dish_count": slot.get("dish_count", 0),
        "dishes": slot.get("dishes", []),
        "candidates": [
            {
                "candidate_id": c.get("candidate_id", ""),
                "name": c.get("name", ""),
                "kcal": c.get("kcal", 0),
                "desc": c.get("desc", ""),
                "dishes": c.get("dishes", []),
            }
            for c in slot.get("candidates", [])
        ],
        "selected_candidate_id": slot.get("selected_candidate_id", ""),
        "micro": slot.get("micro", []),
    }


def meal_card_block(plan: dict) -> dict:
    scope = plan.get("plan_type", "day")
    is_week = scope == "week"
    first_day = plan["days"][0] if plan.get("days") else {"kcal": 0, "slots": []}
    avg = round(sum(d["kcal"] for d in plan.get("days", [])) / max(1, len(plan.get("days", []))))
    candidate_count = len(first_day.get("slots", [{}])[0].get("candidates", [])) if first_day.get("slots") else 0

    goal = plan.get("goal_text", "")
    subtitle = (
        f"目标：{goal} · {plan.get('range_text', '')} · 日均约 {avg} kcal"
        if is_week
        else f"目标：{goal} · 单餐约 {first_day.get('kcal', 0)} kcal · {candidate_count} 个候选"
        if scope == "meal"
        else f"目标：{goal} · 全天约 {first_day.get('kcal', 0)} kcal"
    )
    title = {"week": "📅 一周食谱", "meal": "🍱 午餐搭配", "day": "🗓️ 今日食谱"}.get(scope, "🗓️ 今日食谱")

    return {
        "type": "meal_card",
        "plan_id": plan.get("plan_id", ""),
        "card_id": f"card_{plan.get('plan_id', '')}",
        "title": title,
        "subtitle": subtitle,
        "scope": scope,
        "status": plan.get("status", "draft"),
        "goal_text": plan.get("goal_text", ""),
        "target_kcal": plan.get("goal_energy_kcal", 0),
        "total_kcal": first_day.get("kcal", 0),
        "range_text": plan.get("range_text", ""),
        "slots": [] if is_week else [_slot_view(s) for s in first_day.get("slots", [])],
        "days": [
            {
                "date": d.get("date", ""),
                "weekday": d.get("weekday", ""),
                "is_today": d.get("is_today", False),
                "kcal": d.get("kcal", 0),
                "slots": [_slot_view(s) for s in d.get("slots", [])],
            }
            for d in plan.get("days", [])
        ] if is_week else [],
        "reason": {
            "summary": "按档案与近期微量摄入平衡排出这套方案",
            "points": plan.get("reason_points", []),
        },
        "action_scope_label": {"week": "整周规划", "meal": "这一餐"}.get(scope, "规划"),
    }


def meal_plan_block(plan: dict) -> dict:
    return {
        "type": "meal_plan",
        "plan_id": plan.get("plan_id", ""),
        "view": "week" if plan.get("plan_type") == "week" else "day",
        "title": plan.get("title", ""),
        "subtitle": plan.get("subtitle", ""),
        "days": [
            {
                "date": d.get("date", ""),
                "weekday": d.get("weekday", ""),
                "is_today": d.get("is_today", False),
                "kcal": d.get("kcal", 0),
                "slots": [_slot_view(s) for s in d.get("slots", [])],
            }
            for d in plan.get("days", [])
        ],
    }


def nutrition_block(plan: dict) -> dict:
    return {"type": "nutrition", "plan_id": plan.get("plan_id", ""), **plan.get("nutrition", {})}


def recipe_block(plan: dict) -> dict:
    meals = []
    for s in (plan.get("days", [{}])[0].get("slots", [])):
        meals.append({
            "label": s.get("label", ""),
            "time": s.get("time", ""),
            "color": s.get("color", ""),
            "kcal": s.get("kcal", 0),
            "total": s.get("kcal", 0),
            "dishes": [
                {"name": d.get("name", ""), "amount": d.get("amount", ""),
                 "kcal": d.get("kcal", 0), "tip": d.get("tip", ""), "steps": d.get("steps", [])}
                for d in s.get("dishes", [])
            ],
        })
    return {"type": "recipe_detail", "title": f"{plan.get('title', '')} · 详细食谱", "meals": meals}


def sources_block() -> dict:
    return {"type": "sources", "title": "参考来源", "items": SOURCES}


def anchor_block(items: list[dict]) -> dict:
    return {"type": "anchor", "items": items}


def medical_hint_block(text: str | None = None) -> dict:
    return {
        "type": "medical_hint",
        "level": "warn",
        "title": "这不是医学诊断",
        "text": text or "营养建议只作饮食参考，不能替代检查与诊断。",
        "action_label": "查看参考来源",
    }


def rag_sources_block(items: list[dict]) -> dict:
    """RAG 检索结果 → sources block（用条目里的 source/source_id/title）。"""
    out = []
    for it in items:
        if it.get("title") or it.get("source"):
            out.append({
                "title": it.get("title") or it.get("source") or "",
                "publisher": "",
                "published_at": "",
                "url": it.get("source_id") or "",
                "snippet": (it.get("content") or "")[:120],
            })
    return {"type": "sources", "title": "参考来源", "items": out or SOURCES}


def shopping_list_block(list_dict: dict) -> dict:
    groups = list_dict.get("groups", [])
    total = sum(len(g.get("items", [])) for g in groups)
    return {
        "type": "shopping_list",
        "title": "食材清单",
        "summary": f"共 {total} 项，分 {len(groups)} 组",
        "groups": groups,
    }


def report_block(report: dict) -> dict:
    return {"type": "report", **report, "expanded": False}
