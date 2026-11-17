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
    'report（生成/复盘膳食报告，如「生成周/月膳食报告」「看看这周/这个月吃得怎么样」「复盘这段时间」「复盘 11月1日到11月10日」）、'
    'explain（解释当前方案为什么这样搭/搭配理由）、'
    'reverse_nutrition（症状咨询，如口角炎/乏力/掉发）、chat（闲聊）。\n'
    '注意：只有用户明确要求「生成/推荐/安排 菜单、三餐、食谱」时才归 plan_*；'
    '询问营养知识、食物功效、该怎么吃、忌口建议这类问题一律归 rag_qa；'
    '回顾/复盘一段时间或「吃得怎么样」这类话术归 report。\n'
    'JSON 字段：{"intent":"...", "meal_type":"早餐|午餐|晚餐|null", '
    '"scope":"week|month|plan|null", '
    '"profile":{"gender":"男|女","age":0,"height_cm":0,"weight_kg":0,'
    '"goal_code":"maintain|fat_loss|muscle_gain|glucose_control|digestive_health","allergies":[],"conditions":{},"name":""}}。'
    'report 需填 scope（月→month、周/最近/这段时间→week、自定义日期区间→custom、方案→plan），其余 intent 的 scope 为 null；'
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


# 排版要求（自由文本回复统一注入）：让 LLM 输出紧凑、有层级的 Markdown，配合前端 normalizeSpacing 兜底。
# 仅约束 LLM 文本正文（explain / rag_qa / reverse_nutrition），结构化 block 不受影响。
_FMT = (
    "排版要求（务必遵守，输出要像主流大模型那样简洁美观）：\n"
    "- 小节标题独占一行、用「### 标题」（如「### 能量」「### 蛋白」），不要只写裸文字「能量」；\n"
    "- 标题与正文之间、列表项之间都【不要空行】，连续空行会渲染成大片空白；\n"
    "- 子点用「- 」列表，一条一点，每条 1~2 行，不要每个点都另起一个空行段落；\n"
    "- 关键数值与结论用 **加粗**；禁止「---」分隔线；\n"
    "- 需要表格用「| a | b |」并在下一行写「|---|---|」，不要用制表符。"
)


# 叙事系统指令（结构化动作的正文生成用）：铁律之上加 persona 与「不重复卡片」约束。
_NARRATE_SYSTEM = (
    SYSTEM_INSTRUCTION
    + "\n你是「膳宝」，一个友好、简洁的膳食搭配助手，用「你」称呼用户，语气轻松不生硬。\n"
    "你现在要针对刚刚完成的一个动作写一句到三句的短回应，用自然段落即可，不要用标题、列表或表格。\n"
    "重要：结构化结果（食谱卡片/膳食报告）已经由前端单独渲染，你的文字不要整段复述卡片里的数据，"
    "只需自然点出关键信息（如本餐/本周的核心菜、热量量级、状态变化）并引导下一步。\n"
    "所有数值只能引用「本轮结果」里给出的，不得自行计算或编造。"
)


_DATE_TOKEN_RE = re.compile(
    r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?|(\d{1,2})月(\d{1,2})[日号]"
)


def _parse_date_range(message: str) -> tuple[str, str] | None:
    """从消息里抽取两个日期（YYYY-MM-DD / YYYY年M月D日 / M月D日），返回 (start, end) ISO 串。"""
    tokens: list[date] = []
    year = date.today().year
    for m in _DATE_TOKEN_RE.finditer(message):
        if m.group(1):
            tokens.append(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        else:
            tokens.append(date(year, int(m.group(4)), int(m.group(5))))
    if len(tokens) < 2:
        return None
    start, end = tokens[0], tokens[1]
    if end < start:
        start, end = end, start
    return start.isoformat(), end.isoformat()


def _regex_intent(message: str) -> dict | None:
    m = message.strip()
    has = lambda pat: re.search(pat, m) is not None  # noqa: E731

    if has(r"换一换|更换|换一餐|换个|换掉"):
        label = next((l for l in ("早餐", "午餐", "晚餐") if l in m), "午餐")
        return {"intent": "swap_candidate", "meal_type": label}
    if has(r"选用|就用|选这个|选方案"):
        label = next((l for l in ("早餐", "午餐", "晚餐") if l in m), "午餐")
        return {"intent": "choose_candidate", "meal_type": label, "name": m}
    if has(r"确认|固定|就这个|就它|就选|就这么|定了|替换|覆盖|取代"):
        return {"intent": "confirm", "replace": has(r"替换|覆盖|取代")}
    if has(r"取消|算了|不用了|先不用"):
        return {"intent": "cancel"}
    if has(r"报告|复盘|回顾|总结|吃得(怎么样|如何|怎样|好不好)|饮食(情况|状况|回顾|复盘|怎么样)"):
        rng = _parse_date_range(m)
        if rng:
            return {
                "intent": "report",
                "scope": "custom",
                "period_start": rng[0],
                "period_end": rng[1],
            }
        if has(r"月|30天|30 天|这个月|本月"):
            scope = "month"
        elif has(r"周|七天|7天|一周|这周|本周|最近|一段时间|这段时间|这阵子|近几天"):
            scope = "week"
        else:
            scope = "plan"
        return {"intent": "report", "scope": scope}
    if has(r"完整食谱|详细食谱|做法|步骤"):
        return {"intent": "recipe_detail"}
    if has(r"食材清单|清单|买菜|采购"):
        return {"intent": "shopping_list"}
    # 解释「为什么这样搭」：只认明确追问依据的话术，避免「怎么搭配饮食」这类营养咨询被误判成解释
    if has(r"为什么.*(这样|这么|如此).*(搭|配)|搭配(理由|依据)|配餐(理由|依据)"):
        return {"intent": "explain"}
    if has(r"一周|七天|7天|整周|一周食谱"):
        return {"intent": "plan_week"}
    # 配餐类意图必须带「生成/排/推荐菜单」这类明确动作，不能只靠「推荐/吃什么/食谱/搭配」几个词，
    # 否则「推荐补钙食物」「贫血吃什么」「高血压食谱」这类营养咨询会被误判成配餐、跳出方案。
    if has(r"推荐(一餐|午餐|晚餐|早餐)|来一餐|(午餐|晚餐|早餐)(吃什么|怎么配|推荐)"):
        label = next((l for l in ("早餐", "午餐", "晚餐") if l in m), "午餐")
        return {"intent": "plan_meal", "meal_type": label}
    if has(r"三餐|一日三餐|今天吃|明天吃|生成(食谱|菜单|三餐)|排(食谱|菜单|三餐)"):
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

def _llm_text(system: str, user: str, fallback: str, history: list | None = None, temperature: float = 0.4) -> str:
    client = _llm()
    if client is None:
        return fallback
    messages: list[dict] = [{"role": "system", "content": system}]
    # 多轮上下文：只取 user/assistant 文本轮，role 白名单防注入 tool/system。
    for h in history or []:
        role = h.get("role")
        content = h.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": str(content)})
    messages.append({"role": "user", "content": user})
    try:
        resp = client.chat.completions.create(
            model=config.DEEPSEEK_MODEL,
            messages=messages,
            temperature=temperature,
        )
        return resp.choices[0].message.content.strip() or fallback
    except Exception:
        return fallback


def _narrate(user_message: str, context: str, fallback: str, history: list | None = None) -> str:
    """结构化动作的正文：把「用户原话 + 本轮工具结果」交给 LLM 写成应景短回应；无 LLM 时回退固定话术。"""
    prompt = f"用户消息：{user_message}\n\n本轮结果：\n{context}"
    return _llm_text(_NARRATE_SYSTEM, prompt, fallback, history, temperature=0.6)


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


# 餐次口径归一：中文全称 / 英文 / 单字 → 统一单字（早/午/晚）。
# 用于把「更换早餐候选」里的「早餐」与后端 slot.meal_type 的「早」对上。
_MEAL_KEY = {
    "早餐": "早", "breakfast": "早", "早": "早",
    "午餐": "午", "lunch": "午", "午": "午",
    "晚餐": "晚", "dinner": "晚", "晚": "晚",
}


def _meal_key(label) -> str:
    if not label:
        return ""
    return _MEAL_KEY.get(str(label).strip(), str(label).strip())


def _iter_slots(plan: dict):
    """遍历方案全部餐位：兼容后端 v1.2（顶层 slots）与旧 days/slots 结构。"""
    for s in plan.get("slots") or []:
        yield s
    for day in plan.get("days") or []:
        for s in day.get("slots") or []:
            yield s


def _find_slot(plan: dict, label: str) -> dict | None:
    target = _meal_key(label)
    for s in _iter_slots(plan):
        if _meal_key(s.get("meal_type") or s.get("label") or "") == target:
            return s
    return None


def _slot_dish_text(slot: dict) -> str:
    """后端 slot → 已选候选菜名串（用于换候选后的回执文案）。"""
    picked = slot.get("selected_candidate") or ((slot.get("candidates") or [None])[0])
    dishes = (picked or {}).get("dishes") or []
    return " + ".join(str(d.get("name", "")) for d in dishes)


def _candidate_name(candidate: dict) -> str:
    """后端候选 → 菜名串（与前端 candidateView.name 同构：dishes[].name 用 ' + ' 连接）。

    后端 `_serialize_candidate` 没有 name 字段，菜名在 dishes[].name 里；
    「选用」分支靠它把用户消息里的候选名和方案里的候选对上。
    """
    dishes = (candidate or {}).get("dishes") or []
    return " + ".join(str(d.get("name", "")) for d in dishes)


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


def _plan_brief(plan: dict, limit: int = 6) -> str:
    """从方案抽取供 LLM 包装正文用的关键信息（只读后端已给字段，不自行计算）。"""
    slots = list(_iter_slots(plan))
    lines = []
    for s in slots[:limit]:
        picked = s.get("selected_candidate") or ((s.get("candidates") or [None])[0])
        dishes = (picked or {}).get("dishes") or []
        names = "、".join(str(d.get("name", "")) for d in dishes if d.get("name"))
        kcal = ((picked or {}).get("macro_estimate") or {}).get("kcal")
        kcal_txt = f"约 {kcal} kcal" if kcal is not None else "热量待估"
        meal = s.get("meal_type") or s.get("label") or ""
        if names:
            lines.append(f"{meal}：{names}（{kcal_txt}）")
    if len(slots) > limit:
        lines.append(f"……（共 {len(slots)} 餐，完整内容见卡片）")
    if not lines:
        lines.append("（方案内容见卡片）")
    return "\n".join(lines)


def run(user_id: str, message: str, history: list | None = None) -> dict:
    """执行一条用户消息，返回 {text, blocks}。history 为最近若干轮 user/assistant 文本。"""
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
        base_fallback = {
            # 去掉了对 plan['range_text'] 的依赖，避免后端新 JSON 没有该字段报错
            "plan_week": f"收到！按你的{goal}档案排了接下来七天（{today} 至 {end_day}）的三餐，食材尽量不重复：",
            "plan_meal": "给你挑了三个方向，热量都落在本餐区间，点一个就能确认：",
            "plan_day": f"收到！已结合你的{goal}档案，为你生成了今天的方案：",
        }[kind]
        fallback = base_fallback + "\n(注：以上知识由权威文献提供；生病请及时就医。可在面板中查看当前规划。)"
        scope_label = {"plan_week": "接下来 7 天", "plan_day": "今天", "plan_meal": "一餐"}[kind]
        context = (
            f"动作：为「{scope_label}」生成了配餐方案。\n"
            f"档案目标：{goal}\n"
            f"方案内容：\n{_plan_brief(plan)}\n"
            "引导：右侧「当前规划」面板可查看；餐卡可「换一换」换候选，确认后固定并生成食材清单。"
        )
        text = _narrate(message, context, fallback, history)

        return {
            "text": text,
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
            return {"text": "没找到对应的餐位。", "blocks": []}

        try:
            meal_plan_id = plan.get("meal_plan_id") or plan.get("plan_id")
            # 【修复】swap 接口只回部分结果（candidate + macro_delta），不携带完整 slots；
            # 这里调它只负责落库，完整方案再按 id 重新拉取，避免状态被部分结果覆盖。
            bc.swap_candidate(
                meal_plan_id=meal_plan_id,
                meal_slot_id=slot.get("meal_slot_id") or slot.get("slot_id"),
            )
            updated_plan = bc.get_meal_plan(meal_plan_id)
            st["current_plan"] = updated_plan

            # 拿换好的新菜名 / 热量拼到文字里
            new_slot = _find_slot(updated_plan, intent.get("meal_type") or "午餐")
            new_dish_text = _slot_dish_text(new_slot) if new_slot else "新候选"
            kcal_text = "热量待估"
            if new_slot:
                picked = new_slot.get("selected_candidate") or ((new_slot.get("candidates") or [None])[0])
                k = (picked or {}).get("macro_estimate", {}).get("kcal")
                if k is not None:
                    kcal_text = f"{k} kcal"

            fallback = f"换好啦！给你换成了 {new_dish_text}，这一顿 {kcal_text}。你觉得怎么样？\n(可在面板中查看当前规划)"
            context = (
                f"动作：更换「{intent.get('meal_type') or '午餐'}」候选。\n"
                f"新候选：{new_dish_text}\n"
                f"该餐热量：{kcal_text}\n"
                "引导：卡片已更新，可继续换或确认。"
            )
            text = _narrate(message, context, fallback, history)
            return {
                "text": text,
                # 【核心修改】只发前端认的 meal_card，删掉废弃的 anchor_block
                "blocks": [blocks.meal_card_block(updated_plan)]
            }
        except Exception as e:
            return {"text": f"换候选失败：{e}", "blocks": []}

    # 选用候选
    if kind == "choose_candidate":
        st = _user_state(user_id)
        plan = st.get("current_plan")
        if not plan:
            return {"text": "还没有方案。先生成一份吧。", "blocks": []}

        slot = _find_slot(plan, intent.get("meal_type") or "午餐")
        if not slot:
            return {"text": "没找到这一餐。", "blocks": []}

        # 候选没有 name 字段（菜名在 dishes[].name）。用「菜名串完整出现在消息里」匹配，
        # 取最长命中（最具体）避免子集候选误命中（如单菜「米饭」被「米饭 + 清炒西兰花」抢走）。
        msg = intent.get("name") or ""
        target = None
        for c in slot.get("candidates") or []:
            sig = _candidate_name(c)
            if sig and sig in msg:
                if target is None or len(sig) > len(_candidate_name(target)):
                    target = c
        if not target:
            return {"text": "我没听清是哪个候选，可以把候选名称发我，或直接点候选卡片。",
                    "blocks": []}

        try:
            # 【核心修改】选用指定候选：多传 candidate_id；接口只落库，完整方案再按 id 拉取。
            meal_plan_id = plan.get("meal_plan_id") or plan.get("plan_id")
            bc.swap_candidate(
                meal_plan_id=meal_plan_id,
                meal_slot_id=slot.get("meal_slot_id") or slot.get("slot_id"),
                candidate_id=target.get("candidate_id", ""),
            )
            updated_plan = bc.get_meal_plan(meal_plan_id)
            st["current_plan"] = updated_plan

            kcal = (target.get("macro_estimate") or {}).get("kcal")
            kcal_text = f"{kcal} kcal" if kcal is not None else "热量待估"
            name = _candidate_name(target)
            fallback = f"已选定 {name}，这一顿 {kcal_text}。"
            context = (
                f"动作：选定「{intent.get('meal_type') or '午餐'}」候选。\n"
                f"选定菜品：{name}\n"
                f"该餐热量：{kcal_text}\n"
                "引导：卡片已更新，可继续调整或确认。"
            )
            text = _narrate(message, context, fallback, history)
            return {
                "text": text,
                "blocks": [blocks.meal_card_block(updated_plan)]
            }
        except Exception as e:
            return {"text": f"选用失败：{e}", "blocks": []}

    # 取消（覆盖追问的否定回答）
    if kind == "cancel":
        return {"text": "好的，已保留旧方案，没有改动。", "blocks": []}

    # 确认 / 固定
    if kind == "confirm":
        st = _user_state(user_id)
        plan = st.get("current_plan")
        if not plan:
            return {"text": "现在还没有待确认的方案。我可以先按你的档案排今天的二餐，也可以排一周。", "blocks": []}

        replace = bool(intent.get("replace"))
        try:
            # 【核心修改】调后端接口，把状态改成 fixed 并落库；replace=True 时取代同期旧方案
            updated_plan = bc.fix_meal_plan(
                meal_plan_id=plan.get("meal_plan_id", ""), replace=replace
            )

            st["current_plan"] = updated_plan
            st["plans"].insert(0, dict(updated_plan))

            fallback = (
                f"已确认，方案已生效。{'已取代同期的旧方案。' if replace else ''}\n"
                "食材清单已按类别整理好，点开右侧工具栏的「食材清单」即可查看，还能边买边勾选。"
            )
            context = (
                "动作：确认/固定当前方案。\n"
                f"是否取代同期的旧方案：{'是' if replace else '否'}\n"
                "引导：方案已生效（餐卡翻「已生效」）；食材清单已生成，右侧「食材清单」面板可查看并边买边勾。"
            )
            text = _narrate(message, context, fallback, history)
            return {
                "text": text,
                # 【改进】发带 fixed 状态的餐卡：前端按 meal_plan_id 就地更新原卡（翻成「已生效」并禁用按钮），
                # 不在对话里追加新卡；清单只引导去右侧工具栏。
                "blocks": [blocks.meal_card_block(updated_plan)]
            }
        except bc.BackendError as e:
            if getattr(e, "code", None) == 2005:  # PLAN_STATE_CONFLICT：同期已有固定方案
                # 后端消息已完整（含冲突说明），不再重复追加提示，也不重复渲染方案卡片；
                # 改用行内快捷按钮让用户二选一，点击后发「替换/取消」固定话术走意图路由。
                return {
                    "text": str(e),
                    "blocks": [
                        blocks.quick_actions_block([
                            {"label": "替换", "phrase": "替换"},
                            {"label": "取消", "phrase": "取消"},
                        ])
                    ],
                }
            return {"text": f"确认方案失败：{e}", "blocks": []}
        except Exception as e:
            return {"text": f"确认方案失败：{e}", "blocks": []}

    if kind == "report":
        scope = intent.get("scope") or "plan"

        # 膳食报告（时间段维度）：周/月/自定义，跨方案聚合，不依赖当前方案
        if scope in ("week", "month", "custom"):
            try:
                if scope == "custom":
                    report = bc.period_analysis(
                        "custom",
                        period_start=intent.get("period_start"),
                        period_end=intent.get("period_end"),
                    )
                else:
                    report = bc.period_analysis(scope)
            except Exception as e:
                return {"text": f"膳食报告生成失败：{e}", "blocks": []}
            label = (
                f"{intent.get('period_start')}~{intent.get('period_end')}"
                if scope == "custom"
                else "近 7 天" if scope == "week" else "近 30 天"
            )
            fallback = (
                f"已为你生成{label}膳食报告，覆盖能量、宏量供能比与 7 项关键微量"
                f"（按窗口内已固定方案聚合）。"
            )
            context = (
                f"动作：生成{label}膳食报告。\n"
                "报告维度：能量、宏量供能比、7 项关键微量（按窗口内已固定方案聚合）。\n"
                "引导：报告卡片在下方；右侧「膳食报告」面板可回看历史。"
            )
            text = _narrate(message, context, fallback, history)
            return {
                "text": text,
                "blocks": [blocks.report_block(report)],
            }

        # 方案营养复盘（独立于膳食报告）：复盘当前方案
        st = _user_state(user_id)
        plan = st.get("current_plan")

        if not plan:
            return {"text": "还没有可复盘的方案。先确认一份规划，再复盘这份方案的营养吧。", "blocks": []}

        # 后端方案主键是 meal_plan_id，方案级复盘 report_type=plan。
        plan_id = plan.get("meal_plan_id") or plan.get("plan_id", "")

        try:
            if str(plan_id).isdigit():
                report = bc.nutrition_analysis(int(plan_id))
            else:
                return {"text": "方案还没落库，暂时复盘不了。先确认一份规划吧。", "blocks": []}
        except Exception as e:
            return {"text": f"方案复盘失败：{e}。可能是方案未落库或后端未响应。", "blocks": []}

        fallback = "已为你复盘这份方案的营养，覆盖能量、宏量供能比与 7 项关键微量。"
        context = (
            "动作：复盘当前方案营养。\n"
            "报告维度：能量、宏量供能比、7 项关键微量。\n"
            "引导：报告卡片在下方。"
        )
        text = _narrate(message, context, fallback, history)
        return {
            "text": text,
            "blocks": [blocks.report_block(report)]
        }

    # 完整食谱 / 食材清单
    if kind == "recipe_detail":
        plan = _user_state(user_id).get("current_plan")
        if not plan:
            return {"text": "还没有方案可以展开。要先排今天的三餐吗？", "blocks": []}
        fallback = "完整食谱卡片已送达，每道菜都有估量和热量。"
        context = "动作：展开完整食谱。引导：卡片已更新，每道菜含估量与热量。"
        text = _narrate(message, context, fallback, history)
        # 【修改】原本发 3 种废弃卡片，现在严格遵照清单要求改发 meal_card_block
        return {
            "text": text,
            "blocks": [blocks.meal_card_block(plan)]
        }

    if kind == "shopping_list":
        plan = _user_state(user_id).get("current_plan")
        if not plan or plan.get("status") != "fixed":
            return {
                "text": "方案还没确认，清单暂时是空的。确认后我会按三餐把食材归好类，你可以在右侧工具栏里打开食材清单。",
                "blocks": []}

        fallback = "食材清单已按类别整理好，点开右侧工具栏的「食材清单」即可查看，还能边买边勾选。"
        context = "动作：查看食材清单。引导：清单在右侧「食材清单」面板，可边买边勾。"
        text = _narrate(message, context, fallback, history)
        # 【改进】清单住右侧工具栏：显式索要也只引导去面板，不在对话里贴清单块
        return {
            "text": text,
            "blocks": []
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
            SYSTEM_INSTRUCTION + "\n针对症状咨询：给出可能的营养线索，措辞用「可能缺乏 / 建议关注」，不给定论，并注明仅供参考、不构成诊断、建议就医。" + _FMT,
            f"症状：{message}\n检索线索：{content or '无'}",
            "单看症状无法下结论，建议先就医检查；饮食上注意均衡，可结合档案做针对性调整（仅供参考，不构成诊断）。",
            history,
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
            + "\n用下方方案数据解释「为什么这样搭」。\n"
              "按「能量 / 蛋白 / 微量 / 结构 / 油盐」五条组织，每条 1~3 行，没数据的字段一句话写「该项未提供」，不要空谈；\n"
              "禁止逐字复述餐卡里已展示的数据；结尾 2~3 行总结；不编造、不下达标结论（null≠0，依据码不能代替实测）。\n"
            + _FMT,
            f"用户问：{message}\n方案数据：{json.dumps(material, ensure_ascii=False)}",
            "这套方案是结合你的档案与目标排的：主食打底保证供能，配菜兼顾蛋白质与蔬菜，具体依据如下…",
            history,
        )
        return {"text": text, "blocks": []}

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
            SYSTEM_INSTRUCTION + "\n用检索到的资料回答，结论标注出处，注意双口径（生重/成品）与油盐话术。" + _FMT,
            f"问题：{message}\n检索资料：{content or '无'}",
            "这个问题建议结合权威膳食指南理解；如需针对性建议，我可以按你的档案给出更具体的方案。",
            history,
        )
        # 【修改】停用 rag_sources 卡片，来源通过 LLM 文本呈现
        return {"text": text, "blocks": []}

    # 兜底
    # 【修改】停用 anchor_block
    fallback = "这个我暂时答不好。可以让我按档案排今天的三餐、换一餐的候选、或者生成一份膳食报告。\n(功能面板可在左下角菜单中找到)"
    context = (
        "动作：用户的消息没有命中明确的配餐/调整/报告/营养问答意图。\n"
        "引导：友好回应，并把用户引向可用功能——生成一日三餐 / 一周食谱 / 推荐一餐 / 生成膳食报告 / 咨询营养知识。"
    )
    text = _narrate(message, context, fallback, history)
    return {
        "text": text,
        "blocks": [],
    }


def _week_start() -> str:
    d = date.today()
    return (d - timedelta(days=d.weekday())).isoformat()