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


def _candidate_kcal(candidate: dict | None):
    """候选热量：契约口径在 macro_estimate.kcal；缺失保持 None（null≠0）。"""
    if not candidate:
        return None
    return (candidate.get("macro_estimate") or {}).get("kcal")


def _slot_view(slot: dict) -> dict:
    candidates = [
        {
            "candidate_id": c.get("candidate_id", ""),
            "name": c.get("name", ""),
            "rank": c.get("rank"),
            "why_text": c.get("why_text", ""),
            "reason_codes": c.get("reason_codes", []),
            "macro_estimate": c.get("macro_estimate", {}),
            "micro_estimate": c.get("micro_estimate", {}),
            "oil_salt_estimate": c.get("oil_salt_estimate", {}),
            "eating_order_advice": c.get("eating_order_advice", ""),
            "sources": c.get("sources", []),
            "dishes": c.get("dishes", []),
        }
        for c in slot.get("candidates", [])
    ]

    # 后端 _serialize_slot 直接给 selected_candidate（含 macro_estimate / oil_salt_estimate / dishes）；
    # 老格式（rule_engine_bridge 的 slot 只有 candidates）回退到第一个候选。
    picked = slot.get("selected_candidate") or (candidates[0] if candidates else None)
    picked_dishes = picked.get("dishes", []) if picked else slot.get("dishes", [])
    picked_oil = (picked.get("oil_salt_estimate") or {}) if picked else {}

    return {
        "meal_slot_id": slot.get("meal_slot_id", ""),  # 修改：对齐 v1.2 契约，不用 slot_id
        # 【P0 修复】补 slot_date / display_order / target_macro：前端按 slot_date 分组折叠成天。
        # 缺 slot_date 时前端 groupDays 会把 21 个餐位全归到同一空日期，退化成「一日三餐」平铺。
        "slot_date": slot.get("slot_date", ""),
        "display_order": slot.get("display_order", 1),
        "target_macro": slot.get("target_macro", {}),
        "meal_type": slot.get("meal_type", "午"),
        "label": slot.get("label", ""),
        "time": slot.get("time", ""),
        "color": slot.get("color", ""),
        "kcal": _candidate_kcal(picked) if picked else slot.get("kcal"),
        "oil_g": picked_oil.get("oil_g") if picked else slot.get("oil_g"),
        "salt_g": picked_oil.get("salt_g") if picked else slot.get("salt_g"),
        "dish_text": " + ".join(str(d.get("name", "")) for d in picked_dishes),
        "dish_count": len(picked_dishes),
        "dishes": picked_dishes,
        "candidates": candidates,
        "selected_candidate_id": slot.get("selected_candidate_id", ""),
        "micro": slot.get("micro", []),
    }


def meal_card_block(plan: dict) -> dict:
    scope = plan.get("plan_type", "day")
    is_week = scope == "week"

    # 【核心修复 1】兼容后端新版 v1.2 的 ID 命名：优先取 meal_plan_id
    real_plan_id = plan.get("meal_plan_id") or plan.get("plan_id", "")

    # 【核心修复 2】兼容单日/单餐的 slots 路径：外层没有 days 时，直接去外层找 slots
    days_list = plan.get("days", [])
    root_slots = plan.get("slots", [])
    all_slots = root_slots or [s for day in days_list for s in day.get("slots", [])]
    first_slots = [_slot_view(s) for s in all_slots]
    kcal_vals = [s.get("kcal") for s in first_slots]
    day_kcal = round(sum(kcal_vals), 1) if kcal_vals and all(v is not None for v in kcal_vals) else None
    target_vals = [(s.get("target_macro") or {}).get("kcal") for s in first_slots]
    planned_target = round(sum(target_vals), 1) if target_vals and all(v is not None for v in target_vals) else None

    goal = plan.get("goal_text", "")
    kcal_text = f"约 {day_kcal} kcal" if day_kcal is not None else "热量待估"
    subtitle = f"目标：{goal} · 已安排餐次合计{kcal_text}"
    title = {"week": "📅 一周食谱", "meal": "🍱 午餐搭配", "day": "🗓️ 今日食谱"}.get(scope, "🗓️ 今日食谱")

    return {
        "type": "meal_card",
        # v1.2 契约字段（前端 normalizeMealCard 读这些；后端 _serialize_plan 已是同构格式）
        "meal_plan_id": real_plan_id,
        "display_index": plan.get("display_index"),
        "plan_type": plan.get("plan_type", "日"),
        "status": plan.get("status", "draft"),
        "start_date": plan.get("start_date", ""),
        "end_date": plan.get("end_date", ""),
        "goal_code": plan.get("goal_code", ""),
        "goal_energy_kcal": plan.get("goal_energy_kcal"),
        "macro_ratio": plan.get("macro_ratio") or {},
        "why_summary": plan.get("why_summary", ""),
        "reference_hints": plan.get("reference_hints", []),
        "data_quality_notes": plan.get("data_quality_notes", []),
        "slots": first_slots,
        # 兼容旧字段（chat.py 读 plan_id 回填 done.meal_plan_id；旧调用方读 title/scope/total_kcal）
        "plan_id": real_plan_id,
        "card_id": f"card_{real_plan_id}",
        "title": title,
        "subtitle": subtitle,
        "scope": scope,
        "goal_text": plan.get("goal_text", ""),
        "target_kcal": planned_target,
        "total_kcal": day_kcal,
        "range_text": plan.get("range_text", ""),
        "days": [],
        "reason": {
            "summary": plan.get("why_summary") or "按档案与近期微量摄入平衡排出这套方案",
            "points": plan.get("reason_points", []),
        },
        "action_scope_label": {"week": "整周规划", "meal": "这一餐"}.get(scope, "规划"),
    }


# def meal_plan_block(plan: dict) -> dict:
#     return {
#         "type": "meal_plan",
#         "plan_id": plan.get("plan_id", ""),
#         "view": "week" if plan.get("plan_type") == "week" else "day",
#         "title": plan.get("title", ""),
#         "subtitle": plan.get("subtitle", ""),
#         "days": [
#             {
#                 "date": d.get("date", ""),
#                 "weekday": d.get("weekday", ""),
#                 "is_today": d.get("is_today", False),
#                 "kcal": d.get("kcal", 0),
#                 "slots": [_slot_view(s) for s in d.get("slots", [])],
#             }
#             for d in plan.get("days", [])
#         ],
#     }


# def nutrition_block(plan: dict) -> dict:
#     return {"type": "nutrition", "plan_id": plan.get("plan_id", ""), **plan.get("nutrition", {})}


# def recipe_block(plan: dict) -> dict:
#     meals = []
#     for s in (plan.get("days", [{}])[0].get("slots", [])):
#         meals.append({
#             "label": s.get("label", ""),
#             "time": s.get("time", ""),
#             "color": s.get("color", ""),
#             "kcal": s.get("kcal", 0),
#             "total": s.get("kcal", 0),
#             "dishes": [
#                 {"name": d.get("name", ""), "amount": d.get("amount", ""),
#                  "kcal": d.get("kcal", 0), "tip": d.get("tip", ""), "steps": d.get("steps", [])}
#                 for d in s.get("dishes", [])
#             ],
#         })
#     return {"type": "recipe_detail", "title": f"{plan.get('title', '')} · 详细食谱", "meals": meals}


# def sources_block() -> dict:
#     return {"type": "sources", "title": "参考来源", "items": SOURCES}
#
#
# def anchor_block(items: list[dict]) -> dict:
#     return {"type": "anchor", "items": items}
#
#
# def medical_hint_block(text: str | None = None) -> dict:
#     return {
#         "type": "medical_hint",
#         "level": "warn",
#         "title": "这不是医学诊断",
#         "text": text or "营养建议只作饮食参考，不能替代检查与诊断。",
#         "action_label": "查看参考来源",
#     }
#
#
# def rag_sources_block(items: list[dict]) -> dict:
#     """RAG 检索结果 → sources block（用条目里的 source/source_id/title）。"""
#     out = []
#     for it in items:
#         if it.get("title") or it.get("source"):
#             out.append({
#                 "title": it.get("title") or it.get("source") or "",
#                 "publisher": "",
#                 "published_at": "",
#                 "url": it.get("source_id") or "",
#                 "snippet": (it.get("content") or "")[:120],
#             })
#     return {"type": "sources", "title": "参考来源", "items": out or SOURCES}


def shopping_list_block(list_dict: dict) -> dict:
    groups = list_dict.get("groups", [])
    total = list_dict.get("total_items") or sum(len(g.get("items", [])) for g in groups)
    return {
        "type": "shopping_list",
        "title": "食材清单",
        "summary": f"共 {total} 项，分 {len(groups)} 组",
        "total_items": total,
        "meal_plan_id": list_dict.get("meal_plan_id", ""),
        "groups": groups,
    }


def report_block(report: dict) -> dict:
    # block type 用 "report"：后端 chat.py 的 _ARTIFACT_TYPE_MAP 把 "report" 映射成
    # 契约 artifact "nutrition_report"；直接发 "nutrition_report" 会被当未知 type 丢弃。
    # 这里原样透传后端 /nutrition/analysis 的方案级报告，由前端 normalizeReport 渲染。
    return {"type": "report", **report, "expanded": False}


def quick_actions_block(actions: list[dict]) -> dict:
    """行内快捷按钮：点击发固定话术（phrase）走 SSE，由 Agent 意图路由。

    用于「替换 / 取消」这类需要用户做二选一决定的追问，前端渲染成按钮。
    actions 形如 [{"label": "替换", "phrase": "替换"}, ...]。
    """
    return {"type": "quick_actions", "actions": actions}
