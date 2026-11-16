# -*- coding: utf-8 -*-
"""Agent 编排核心：意图路由 + 确定性执行 + LLM 增值。

设计（对齐 v2.0「确定性计算与智能决策分离」）：
- 生成 / 换候选 / 确认 / 报告 等**结构化动作**走确定性路由（正则 + rule_engine / 后端 REST），
  LLM 不参与算数，只补自然语言；
- 知识问答 / 症状咨询 / 建档 等**自由输入**用 LLM 分类与组织语言，但数值结论仍来自工具。
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta

import backend_client as bc
import blocks
import config
import rule_engine_bridge as reb

# ---------------------------------------------------------------- 内存态（多轮：换候选/确认）

_state: dict[str, dict] = {}  # user_id -> {"current_plan": dict, "plans": [dict]}


def _user_state(user_id: str) -> dict:
    return _state.setdefault(user_id, {"current_plan": None, "plans": []})


# ---------------------------------------------------------------- LLM 客户端（可选）

_client = None
_client_checked = False


def _llm():
    global _client, _client_checked
    if _client_checked:
        return _client
    _client_checked = True
    if not config.DEEPSEEK_API_KEY or config.DEEPSEEK_API_KEY.startswith("sk-xxx"):
        _client = None
        return None
    try:
        from openai import OpenAI
        _client = OpenAI(api_key=config.DEEPSEEK_API_KEY, base_url=config.DEEPSEEK_BASE_URL)
    except Exception:
        _client = None
    return _client


def llm_available() -> bool:
    return _llm() is not None


# ---------------------------------------------------------------- 意图分类

_INTENT_SYSTEM = (
    "你是膳食搭配智能体的意图分类器。把用户消息归入一个意图，只返回 JSON，不要多余文字。\n"
    '意图：plan_day（今日/某天一日三餐）、plan_week（一周食谱）、plan_meal（单餐推荐）、'
    'profile_build（用户描述身体指标/目标/过敏，需建档）、rag_qa（营养知识问答）、'
    'explain（解释当前方案为什么这样搭/搭配理由）、'
    'reverse_nutrition（症状咨询，如口角炎/乏力/掉发）、chat（闲聊）。\n'
    'JSON 字段：{"intent":"...", "meal_type":"早餐|午餐|晚餐|null", '
    '"profile":{"gender":"男|女","age":0,"height_cm":0,"weight_kg":0,'
    '"goal_code":"maintain|fat_loss|muscle_gain|glucose_control|digestive_health","allergies":[],"conditions":{},"name":""}}。'
    '仅 profile_build 需要填 profile，其余为 null。'
)


# 系统指令（回复生成时统一注入）：8 条共享铁律 + 4 处需求约束（FR-19/20/21/29）
SYSTEM_INSTRUCTION = (
    "你是「膳食搭配智能体」，负责营养配餐与营养答疑。遵守以下铁律：\n"
    "1) 零编造：所有数值（能量/营养素/油盐/参考值）一律来自工具或后端返回，绝不自己计算、不估算、不编造。\n"
    "2) 硬约束优先：过敏原与疾病忌口是硬约束，优先于用户口头偏好。\n"
    "3) 可溯源：营养结论标注出处（source/source_id）。\n"
    "4) null≠0：字段为空表示未知，不得当 0 判达标/超标，回复「无法判断 / 需复核」。\n"
    "5) data_quality 语义：仅 official 为官方实测；approx/check 不得当实测下结论。\n"
    "6) 未核查≠安全：allergen_status=未核查 的食材/菜式不得宣称「安全」。\n"
    "7) needs_clarification=true 时必须追问用户，不得自行取值。\n"
    "8) 不做医学诊断。\n"
    "9) 双口径（FR-19/20）：食材营养按「生重」、菜式按「成品」展示，回复中两种口径必须分别标明，不得混用。\n"
    "10) 油盐表述（FR-21）：用「低 / 中 / 高 + 大致克数区间」描述油盐，不给出伪精确的克数。\n"
    "11) 措辞（FR-29）：症状 / 用药相关结论用「可能缺乏 / 建议关注」，不给定论；反向营养仅作参考线索。\n"
)


def _regex_intent(message: str) -> dict | None:
    m = message.strip()
    has = lambda pat: re.search(pat, m) is not None  # noqa: E731

    if has(r"换一换|更换|换一餐|换个|换掉"):
        label = next((l for l in ("早餐", "午餐", "晚餐") if l in m), "午餐")
        return {"intent": "swap_candidate", "meal_type": label}
    if has(r"选用|就用|选这个|选方案"):
        label = next((l for l in ("早餐", "午餐", "晚餐") if l in m), "午餐")
        return {"intent": "choose_candidate", "meal_type": label, "name": m}
    if has(r"确认|固定|就这个|可以了|没问题"):
        return {"intent": "confirm"}
    if has(r"报告|复盘"):
        scope = "month" if has(r"月|30天|30 天") else "week"
        return {"intent": "report", "scope": scope}
    if has(r"完整食谱|详细食谱|做法|步骤"):
        return {"intent": "recipe_detail"}
    if has(r"食材|清单|买菜|采购"):
        return {"intent": "shopping_list"}
    if has(r"为什么.*(这样|这么|如此).*(搭|配)|搭配(理由|依据)|配餐(理由|依据)|怎么搭|搭配讲究"):
        return {"intent": "explain"}
    if has(r"一周|七天|7天|整周|一周食谱"):
        return {"intent": "plan_week"}
    if has(r"一餐|推荐|午餐|晚餐|早餐") and not has(r"三餐|一日"):
        label = next((l for l in ("早餐", "午餐", "晚餐") if l in m), "午餐")
        return {"intent": "plan_meal", "meal_type": label}
    if has(r"三餐|一日|今天|明天|吃什么|搭配|配餐|食谱"):
        return {"intent": "plan_day"}
    return None


def _llm_classify(message: str) -> dict:
    client = _llm()
    if client is None:
        return {"intent": "chat"}
    try:
        resp = client.chat.completions.create(
            model=config.DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": _INTENT_SYSTEM},
                {"role": "user", "content": message},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        raw = resp.choices[0].message.content
        return json.loads(raw)
    except Exception:
        return {"intent": "chat"}


def classify(message: str) -> dict:
    r = _regex_intent(message)
    if r:
        return r
    if re.search(r"症状|缺什么|乏力|掉发|头晕|抽筋|便秘|口角炎|夜盲", message):
        return {"intent": "reverse_nutrition"}
    return _llm_classify(message)


# ---------------------------------------------------------------- LLM 文本

def _llm_text(system: str, user: str, fallback: str) -> str:
    client = _llm()
    if client is None:
        return fallback
    try:
        resp = client.chat.completions.create(
            model=config.DEEPSEEK_MODEL,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.4,
        )
        return resp.choices[0].message.content.strip() or fallback
    except Exception:
        return fallback


# ---------------------------------------------------------------- 档案

def _load_profile(user_id: str) -> dict | None:
    try:
        return bc.get_profile(user_id)
    except Exception:
        return None


def _goal_text(profile: dict) -> str:
    extras = profile.get("extras") or {}
    goals = extras.get("goals") or []
    if goals:
        return "、".join(goals)
    return profile.get("goal") or "维持"


# ---------------------------------------------------------------- 方案动作

def _gen(user_id: str, params: dict, profile: dict) -> dict:
    plan = reb.generate_plan_dict(user_id, profile, params)
    _user_state(user_id)["current_plan"] = plan
    return plan


def _shopping_list(plan: dict) -> dict:
    """由方案聚合出食材清单（按简单类别分组）。"""
    cat_of = {}
    groups: dict[str, dict] = {}
    for day in plan.get("days", []):
        for slot in day.get("slots", []):
            for d in slot.get("dishes", []):
                name = d["name"]
                cat = cat_of.get(name)
                if cat is None:
                    n = name
                    if re.search(r"菜|瓜|茄|椒|芦笋|木耳|海带|菌|菇|笋|菠菜|芥蓝|空心菜|油麦菜|娃娃菜|包菜|西兰花|萝卜|白菜", n):
                        cat = "🥬 蔬菜类"
                    elif re.search(r"鸡|牛|猪|鱼|虾|肉|排|三文鱼|鳕鱼|鲈鱼|龙利鱼|鸡胸|鸡腿|排骨|蛋", n):
                        cat = "🍗 肉禽蛋水产"
                    elif re.search(r"米|面|吐司|馒头|红薯|玉米|藜麦|燕麦|小米|麦|饼|面包", n):
                        cat = "🌾 主食杂粮"
                    elif re.search(r"蓝莓|苹果|香蕉|橙子|牛油果|核桃|杏仁|莓|梨", n):
                        cat = "🍎 水果坚果"
                    elif re.search(r"豆浆|酸奶|牛奶|豆腐|豆", n):
                        cat = "🥛 奶豆饮品"
                    else:
                        cat = "🧂 其他"
                    cat_of[name] = cat
                g = groups.setdefault(cat, {"category": cat, "items": []})
                if not any(it["name"] == name for it in g["items"]):
                    g["items"].append({"item_id": f"it-{cat}-{name}", "name": name,
                                       "amount": d.get("amount", ""), "is_staple": bool(d.get("is_staple")),
                                       "checked": False})
    return {"meal_plan_id": plan.get("plan_id", ""), "groups": list(groups.values())}


def _find_slot(plan: dict, label: str) -> dict | None:
    for day in plan.get("days", []):
        for s in day.get("slots", []):
            if label in s.get("label", "") or label in s.get("meal_type", ""):
                return s
    return None


# ---------------------------------------------------------------- 主执行


def _explain_material(plan: dict) -> dict:
    """从当前方案抽取「为什么这样搭」的解释素材（只取后端/规则引擎给的数据，不自行计算）。"""
    meals = []
    for s in plan.get("slots", []):
        picked = s.get("selected_candidate") or (s.get("candidates") or [None])[0]
        if not picked:
            continue
        macro = picked.get("macro_estimate") or {}
        meals.append({
            "餐次": s.get("meal_type"),
            "菜": [f"{d.get('name', '')}（{d.get('portion_text', '')}）" for d in picked.get("dishes", [])],
            "能量_kcal": macro.get("kcal"),
            "蛋白_g": macro.get("protein_g"),
            "脂肪_g": macro.get("fat_g"),
            "碳水_g": macro.get("carb_g"),
            "膳食纤维_g": macro.get("fiber_g"),
            "搭配说明": picked.get("why_text"),
            "依据码": picked.get("reason_codes"),
            "进食顺序建议": picked.get("eating_order_advice"),
        })
    return {
        "目标能量_kcal": plan.get("goal_energy_kcal"),
        "plan_type": plan.get("plan_type"),
        "meals": meals,
    }


def run(user_id: str, message: str) -> dict:
    """执行一条用户消息，返回 {text, blocks}。"""
    intent = classify(message)
    kind = intent.get("intent", "chat")
    profile = _load_profile(user_id)

    # 建档：用户描述自身指标
    if kind == "profile_build":
        p = intent.get("profile") or {}
        if p.get("name"):
            new_id = "u_" + re.sub(r"[^a-z0-9]", "", p["name"].lower()) or "u_" + date.today().strftime("%Y%m%d")
        else:
            new_id = user_id
        try:
            bc.upsert_profile(
                new_id,
                gender=p.get("gender"), age=p.get("age"), height_cm=p.get("height_cm"),
                weight_kg=p.get("weight_kg"), goal_code=p.get("goal_code"),
                allergies=p.get("allergies") or [], taboos=p.get("taboos") or [],
                conditions=p.get("conditions") or {},
                extras={"name": p.get("name") or ""},
            )
            profile = _load_profile(new_id)
            user_id = new_id
        except Exception:
            pass
        if profile is None:
            return {"text": "我还不太了解你的身体情况，可以告诉我性别、年龄、身高体重和目标吗？", "blocks": []}
        kind = "plan_day"  # 建档后默认出当天方案

    # 生成方案
    if kind in ("plan_day", "plan_week", "plan_meal"):
        if profile is None:
            return {"text": "还没有你的档案。可以先告诉我：性别、年龄、身高体重、目标和过敏，我建档后马上配餐。 ",
                    "blocks": []}

        scope = {"plan_day": "day", "plan_week": "week", "plan_meal": "meal"}[kind]

        try:
            # 1. 构造真实后端的日期参数
            today = date.today()
            end_day = today + timedelta(days=6) if scope == "week" else today

            # 映射餐位英文（兼容后端标准枚举）
            mt_map = {"早餐": "breakfast", "午餐": "lunch", "晚餐": "dinner"}
            req_meal_types = ["breakfast", "lunch", "dinner"] if scope != "meal" else [
                mt_map.get(intent.get("meal_type", ""), "lunch")]

            # 2. 【核心替换】直接走网络请求调后端真实 API，确保方案落库并生成真实的 ID！
            plan = bc.generate_meal_plan(
                user_id=user_id,
                scope=scope,
                start_date=str(today),
                end_date=str(end_day),
                meal_types=req_meal_types
            )
            # 生成后写入内存态，供「换候选 / 确认」读取（重构漏写这行会导致确认时报「还没有待确认的方案」）
            _user_state(user_id)["current_plan"] = plan
        except Exception as e:
            return {"text": f"方案没排出来：{e}", "blocks": []}

        goal = _goal_text(profile)
        if kind == "plan_week":
            # 去掉了对 plan['range_text'] 的依赖，避免后端新 JSON 没有该字段报错
            text = f"收到！按你的{goal}档案排了接下来七天（{today} 至 {end_day}）的三餐，食材尽量不重复："
        elif kind == "plan_meal":
            text = "给你挑了三个方向，热量都落在本餐区间，点一个就能确认："
        else:
            text = f"收到！已结合你的{goal}档案，为你生成了今天的方案："

        return {
            "text": text + "\n(注：以上知识由权威文献提供；生病请及时就医。可在面板中查看当前规划。)",
            "blocks": [
                blocks.meal_card_block(plan)
            ],
        }

    # 换候选
    if kind == "swap_candidate":
        st = _user_state(user_id)
        plan = st.get("current_plan")
        if not plan:
            return {"text": "您还没有待确认的方案，要不要先生成今天的配餐？", "blocks": []}

        # 找到要换的是哪一餐
        slot = _find_slot(plan, intent.get("meal_type") or "午餐")
        if not slot:
            return {"text": "没找到对应的餐位。", "blocks": [blocks.meal_card_block(plan)]}

        try:
            # 【核心修改】不自己在内存算了，直接调后端接口落库，并拿到最新的方案！
            updated_plan = bc.swap_candidate(
                meal_plan_id=plan.get("meal_plan_id", ""),
                meal_slot_id=slot.get("meal_slot_id", "")
            )

            # 把后端返回的最新方案更新到会话状态里
            st["current_plan"] = updated_plan

            # 拿换好的新菜名拼到文字里
            new_slot = _find_slot(updated_plan, intent.get("meal_type") or "午餐")
            new_dish_text = new_slot.get("dish_text", "新候选")

            return {
                "text": f"换好啦！给你换成了 {new_dish_text}，这一顿 {new_slot.get('kcal')} kcal。你觉得怎么样？\n(可在面板中查看当前规划)",
                # 【核心修改】只发前端认的 meal_card，删掉废弃的 anchor_block
                "blocks": [blocks.meal_card_block(updated_plan)]
            }
        except Exception as e:
            return {"text": f"换候选失败：{e}", "blocks": [blocks.meal_card_block(plan)]}

    # 选用候选
    if kind == "choose_candidate":
        st = _user_state(user_id)
        plan = st.get("current_plan")
        if not plan:
            return {"text": "还没有方案。先生成一份吧。", "blocks": []}

        slot = _find_slot(plan, intent.get("meal_type") or "午餐")
        if not slot:
            return {"text": "没找到这一餐。", "blocks": [blocks.meal_card_block(plan)]}

        target = next((c for c in slot["candidates"] if c["name"] in (intent.get("name") or "")), None)
        if not target:
            return {"text": "我没听清是哪个候选，可以把候选名称发我，或直接点候选卡片。",
                    "blocks": [blocks.meal_card_block(plan)]}

        try:
            # 【核心修改】选用指定的菜，要多传一个 candidate_id 给后端
            updated_plan = bc.swap_candidate(
                meal_plan_id=plan.get("meal_plan_id", ""),
                meal_slot_id=slot.get("meal_slot_id", ""),
                candidate_id=target.get("candidate_id", "")
            )

            st["current_plan"] = updated_plan

            return {
                "text": f"已选定 {target['name'].split('(')[-1].strip()}，这一餐 {target['kcal']} kcal。",
                "blocks": [blocks.meal_card_block(updated_plan)]
            }
        except Exception as e:
            return {"text": f"选用失败：{e}", "blocks": [blocks.meal_card_block(plan)]}

    # 确认 / 固定
    if kind == "confirm":
        st = _user_state(user_id)
        plan = st.get("current_plan")
        if not plan:
            return {"text": "现在还没有待确认的方案。我可以先按你的档案排今天的二餐，也可以排一周。", "blocks": []}

        try:
            # 【核心修改】调后端接口，把状态改成 fixed 并落库
            updated_plan = bc.fix_meal_plan(meal_plan_id=plan.get("meal_plan_id", ""))

            st["current_plan"] = updated_plan
            st["plans"].insert(0, dict(updated_plan))

            # 清单生成（保持原样即可，前端认 shopping_list_block）
            shop = _shopping_list(updated_plan)
            total = sum(len(g["items"]) for g in shop["groups"])

            return {
                "text": f"已确认，方案已生效。食材清单共 {total} 项，按类别分好了。\n(点击左下角菜单可查看历史方案与食材清单)",
                # 【核心修改】保留 meal_card 和 shopping_list，删掉废弃的 anchor_block
                "blocks": [
                    blocks.meal_card_block(updated_plan),
                    blocks.shopping_list_block(shop)
                ]
            }
        except Exception as e:
            return {"text": f"确认方案失败：{e}", "blocks": [blocks.meal_card_block(plan)]}

    if kind == "report":
        scope = intent.get("scope", "week")
        st = _user_state(user_id)
        plan = st.get("current_plan")

        if not plan:
            # 【修改】去掉了 anchor_block，改用文字引导
            return {"text": "还没有可复盘的方案。先确认一份规划，再在面板里生成报告吧。", "blocks": []}

        plan_id = plan.get("plan_id", "")

        try:
            if str(plan_id).isdigit():
                report = bc.nutrition_analysis(int(plan_id))
            else:
                report = {
                    "period_start": plan.get("plan_date", ""),
                    "summary": {"reference_hints": ["此为离线预览报告，方案落库后可查看精准微量分析。"]},
                    "key_micro_summary": {}
                }
        except Exception as e:
            # 【修改】去掉了 anchor_block
            return {"text": f"报告生成失败：{e}。可能是方案未落库或后端未响应。", "blocks": []}

        rb = _report_dict(report, scope)
        # 【修改】只留 report_block（它会在 blocks.py 里发合规的 nutrition_report），删掉来源和锚点卡片
        return {
            "text": f"已为你生成{'本周' if scope == 'week' else '本次方案'}膳食报告。\n(注：完整数据请在右侧面板查看)",
            "blocks": [blocks.report_block(rb)]
        }

    # 完整食谱 / 食材清单
    if kind == "recipe_detail":
        plan = _user_state(user_id).get("current_plan")
        if not plan:
            return {"text": "还没有方案可以展开。要先排今天的三餐吗？", "blocks": []}
        # 【修改】原本发 3 种废弃卡片，现在严格遵照清单要求改发 meal_card_block
        return {
            "text": "完整食谱卡片已送达，每道菜都有估量和热量。",
            "blocks": [blocks.meal_card_block(plan)]
        }

    if kind == "shopping_list":
        plan = _user_state(user_id).get("current_plan")
        if not plan or plan.get("status") != "fixed":
            # 【修改】去掉了 anchor_block
            return {
                "text": "方案还没确认，清单暂时是空的。确认后我会按三餐把食材归好类，你可以在菜单里打开食材清单。",
                "blocks": []}

        shop = _shopping_list(plan)
        total = sum(len(g["items"]) for g in shop["groups"])
        # 【修改】只发 shopping_list_block
        return {
            "text": f"清单已经整理好，共 {total} 项，按类别分好了。\n(点击左下角菜单可查看完整食材清单)",
            "blocks": [blocks.shopping_list_block(shop)]
        }

    # 反向营养 / 症状咨询
    if kind == "reverse_nutrition":
        try:
            r = bc.reverse_nutrition(message, 5)
            items = r.get("items", [])
            content = "；".join((it.get("content") or it.get("title") or "")[:120] for it in items[:3])
        except Exception:
            content = ""

        text = _llm_text(
            SYSTEM_INSTRUCTION + "\n针对症状咨询：给出可能的营养线索，措辞用「可能缺乏 / 建议关注」，不给定论，并注明仅供参考、不构成诊断、建议就医。",
            f"症状：{message}\n检索线索：{content or '无'}",
            "单看症状无法下结论，建议先就医检查；饮食上注意均衡，可结合档案做针对性调整（仅供参考，不构成诊断）。",
        )
        # 【修改】就医提醒和文献来源已由 LLM 融入正文，不再发废弃的 medical_hint 和 sources 卡片
        return {"text": text + "\n\n(注：以上信息由文献库提供参考，不可替代专业医疗诊断，如有不适请及时就医。)",
                "blocks": []}

    # 知识问答
    # 解释「为什么这样搭」
    if kind == "explain":
        plan = _user_state(user_id).get("current_plan")
        if not plan:
            return {
                "text": "现在还没有配好的方案，我暂时没有可解释的依据。先让我按你的档案排一餐或一日三餐，我再解释为什么这样搭。",
                "blocks": [],
            }
        material = _explain_material(plan)
        text = _llm_text(
            SYSTEM_INSTRUCTION
            + "\n用下方方案数据解释「为什么这样搭」：逐条对应数据（能量/蛋白/微量/结构/油盐），只引用给定字段，没有的写「该项未提供」，不要编造。",
            f"用户问：{message}\n方案数据：{json.dumps(material, ensure_ascii=False)}",
            "这套方案是结合你的档案与目标排的：主食打底保证供能，配菜兼顾蛋白质与蔬菜，具体依据如下…",
        )
        return {"text": text, "blocks": [blocks.meal_card_block(plan)]}

    if kind == "rag_qa":
        try:
            r = bc.rag_query(message, 5)
            items = r.get("items", [])
            content = "；".join((it.get("content") or it.get("title") or "")[:160] for it in items[:3])
            sources = items
        except Exception:
            content = ""
            sources = []

        text = _llm_text(
            SYSTEM_INSTRUCTION + "\n用检索到的资料回答，结论标注出处，注意双口径（生重/成品）与油盐话术。",
            f"问题：{message}\n检索资料：{content or '无'}",
            "这个问题建议结合权威膳食指南理解；如需针对性建议，我可以按你的档案给出更具体的方案。",
        )
        # 【修改】停用 rag_sources 卡片，来源通过 LLM 文本呈现
        return {"text": text, "blocks": []}

    # 兜底
    # 【修改】停用 anchor_block
    return {
        "text": "这个我暂时答不好。可以让我按档案排今天的三餐、换一餐的候选、或者生成一份膳食报告。\n(功能面板可在左下角菜单中找到)",
        "blocks": [],
    }


def _week_start() -> str:
    d = date.today()
    return (d - timedelta(days=d.weekday())).isoformat()


def _report_dict(report: dict, scope: str) -> dict:
    """后端新版方案级营养报告 -> report block 数据。"""
    micro_summary = report.get("key_micro_summary") or {}
    micro_items = []

    # 适配新版 API 返回的字典结构
    for k, v in micro_summary.items():
        pct = v.get("covered_pct") or 0
        status = "ok" if pct >= 80 else "warn" if pct >= 50 else "danger"
        if v.get("status") == "参考提示":
            status = "ok"

        micro_items.append({
            "name": v.get("name_zh") or k,
            "value": f"{pct}%" if pct else "—",
            "ring_percent": pct,
            "status": status,
            "note": v.get("status") or "详见周报"
        })

    summary = report.get("summary") or {}
    hints = summary.get("reference_hints") or []

    return {
        "report_id": f"report_{report.get('nutrition_report_id', 'mock')}",
        "scope": scope,
        "headline": "本周膳食报告" if scope == "week" else "方案膳食报告",
        "meta": {"range_start": report.get("period_start", ""), "range_end": report.get("period_end", ""),
                 "generated_at": date.today().isoformat(), "valid_days": 0, "total_meals": 0,
                 "target_kcal": 0},
        "summary_text": hints[0] if hints else "微量元素平衡已分析。",
        "macro": {"center_value": "0", "center_label": "kcal 日均", "segments": []},
        "micro": {"title": "关键微量元素覆盖", "items": micro_items},
        "daily_trend": [],
        "insights": hints[:3],
    }