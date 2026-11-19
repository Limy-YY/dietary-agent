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
import local_edits as le
import regenerate_flow as rf
import conversation_state as cs
import target_resolver as tr

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
    'plan_custom（自定义范围配餐：N 天、指定日期区间、指定餐次子集，如「三天」「下周一三五」「这周末两天」「只排午餐」）、'
    'profile_build（用户描述身体指标/目标/过敏，需建档）、rag_qa（营养知识问答）、'
    'report（生成/复盘膳食报告，如「生成周/月膳食报告」「看看这周/这个月吃得怎么样」「复盘这段时间」「复盘 11月1日到11月10日」）、'
    'explain（解释当前方案为什么这样搭/搭配理由）、'
    'reverse_nutrition（症状咨询，如口角炎/乏力/掉发）、chat（闲聊）。\n'
    '注意：只有用户明确要求「生成/推荐/安排 菜单、三餐、食谱」时才归 plan_*；'
    '「一周/七天/7天」归 plan_week，「今天/明天一日三餐」归 plan_day，「推荐一餐」归 plan_meal，'
    '其余非标准范围（N 天、自定义日期、指定餐次子集）归 plan_custom；'
    '询问营养知识、食物功效、该怎么吃、忌口建议这类问题一律归 rag_qa；'
    '回顾/复盘一段时间或「吃得怎么样」这类话术归 report。\n'
    'JSON 字段：{"intent":"...", "meal_type":"早餐|午餐|晚餐|null", '
    '"scope":"week|month|plan|null", '
    '"start_date":"YYYY-MM-DD|null", "end_date":"YYYY-MM-DD|null", '
    '"meal_types":["早餐","午餐","晚餐"]|null, '
    '"profile":{"gender":"男|女","age":0,"height_cm":0,"weight_kg":0,'
    '"goal_code":"maintain|fat_loss|muscle_gain|glucose_control|digestive_health","allergies":[],"conditions":{},"name":""}}。'
    'plan_custom 必须按下方规则填 start_date/end_date/meal_types，抽不出才留 null，绝不能编造日期：'
    '「今天」=今天日期，「明天」=明天，「三天/接下来三天」=从今天起连续 3 天，'
    '「下周一到周三」=下周对应具体日期（只排到周三就只排那几天），'
    '「只排午餐」=meal_types 只含「午餐」，「早晚餐」=["早餐","晚餐"]，没提餐次=["早餐","午餐","晚餐"]。'
    'report 需填 scope（月→month、周/最近/这段时间→week、自定义日期区间→custom、方案→plan），其余 intent 的 scope 为 null；'
    '仅 profile_build 需要填 profile，其余为 null。'
)


# 系统指令（回复生成时统一注入）：8 条共享铁律 + 4 处需求约束（FR-19/20/21/29）
SYSTEM_INSTRUCTION = (
    "你是「膳宝」，一个友好、简洁的膳食搭配助手：用「你」称呼用户，语气轻松不生硬，回复直接给结论、不堆客套话。"
    "你负责营养配餐与营养答疑。遵守以下铁律：\n"
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


# 排版要求（自由文本回复统一注入）：让 LLM 输出紧凑、有层级、结论先行的 Markdown，配合前端 normalizeSpacing 兜底。
# 仅约束 LLM 文本正文（explain / rag_qa / reverse_nutrition），结构化 block 不受影响。
_FMT = (
    "排版要求（务必遵守，输出要像主流大模型那样简洁美观）：\n"
    "- 结论先行：第一句直接回答用户、点明主旨，不要客套铺垫；\n"
    "- 小节标题独占一行、用「### 标题」；标题图标由前端自动加，你【不要】自己加 emoji；\n"
    "- 标题与正文之间、列表项之间都【不要空行】，连续空行会渲染成大片空白；\n"
    "- 要点用「- 」列表，一条一点，每条尽量 1 行、最多 2 行；\n"
    "- 多组数值优先用表格「| a | b |」+ 下一行「|---|---|」，不要用制表符；\n"
    "- 关键数值与结论用 **加粗**；禁止「---」分隔线；\n"
    "- 口径/免责类说明（如「成品口径」「仅供参考」）放到最后一行小字，不要在正文反复强调。"
)


# 叙事系统指令（结构化动作的正文生成用）：铁律之上加 persona 与「不重复卡片」约束。
_NARRATE_SYSTEM = (
    SYSTEM_INSTRUCTION
    + "\n你现在要针对刚刚完成的一个动作写一句到三句的短回应，用自然段落即可，不要用标题、列表或表格。\n"
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


def _is_custom_span(m: str) -> bool:
    """是否「自定义范围」配餐请求（应 defer 给 LLM 抽 start_date/end_date/meal_types，正则不抢先）。"""
    if not m:
        return False
    # 明确天数：3天 / 三天 / 五天 / 10天（「1天/一天」是单日、「7天/七天」是周，不算自定义）
    mm = re.search(r"([0-9一二三四五六七八九十两]+)\s*[天日]", m)
    if mm and mm.group(1) not in ("1", "一", "7", "七"):
        return True
    # 显式日期区间（如「11月1日到11月10日」）
    if _parse_date_range(m) is not None:
        return True
    # 周末 / 下周 / 工作日
    if re.search(r"周末|下周|工作日", m):
        return True
    # 「一周/七天/7天 + 指定餐次子集」（如「一周的午餐」「七天早晚餐」）：范围词后出现早/午/晚任一餐次字
    if re.search(r"(一周|七天|7天|整周)\s*的?\s*[早午晚]", m):
        return True
    return False


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
    # 自定义范围（N 天 / 日期区间 / 周末 / 下周 / 指定餐次子集）交给 LLM 抽参数，正则不抢先
    if _is_custom_span(m):
        return None
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
                {"role": "system", "content": _INTENT_SYSTEM + f"\n今天是 {date.today().isoformat()}。"},
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

def _llm_reply(system: str, prompt: str, fallback: str, history: list | None = None, temperature: float = 0.4) -> dict:
    """构造 LLM 叙事请求（不真正调用）；真正调用与逐 token 流式由 main.py 的 stream_reply 做。"""
    messages: list[dict] = [{"role": "system", "content": system}]
    # 多轮上下文：只取 user/assistant 文本轮，role 白名单防注入 tool/system。
    for h in history or []:
        role = h.get("role")
        content = h.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": str(content)})
    messages.append({"role": "user", "content": prompt})
    return {"messages": messages, "temperature": temperature, "fallback": fallback}


def _narrate(user_message: str, context: str, fallback: str, history: list | None = None) -> dict:
    """结构化动作的正文：把「用户原话 + 本轮工具结果」交给 LLM 写成应景短回应（叙事请求，延迟到流式层执行）。"""
    prompt = f"用户消息：{user_message}\n\n本轮结果：\n{context}"
    return _llm_reply(_NARRATE_SYSTEM, prompt, fallback, history, temperature=0.6)


def stream_reply(narration: dict) -> "Iterator[str]":
    """把叙事请求变成逐 token 文本流；无 LLM / 出错时整体回退 fallback（一次性 yield）。"""
    fallback = narration.get("fallback") or ""
    client = _llm()
    if client is None:
        if fallback:
            yield fallback
        return
    emitted = False
    try:
        stream = client.chat.completions.create(
            model=config.DEEPSEEK_MODEL,
            messages=narration["messages"],
            temperature=narration.get("temperature", 0.4),
            stream=True,
        )
        for chunk in stream:
            delta = ""
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                delta = chunk.choices[0].delta.content
            if delta:
                emitted = True
                yield delta
    except Exception:
        pass
    if not emitted and fallback:
        yield fallback


# ---------------------------------------------------------------- 档案

def _load_profile(user_id: str) -> dict | None:
    try:
        return bc.get_profile(user_id)
    except Exception:
        return None


# ---------------------------------------------------------------- 方案动作

def _gen(user_id: str, params: dict, profile: dict, state: dict) -> dict:
    plan = reb.generate_plan_dict(user_id, profile, params)
    le.remember(state, plan)
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
    matches = [s for s in _iter_slots(plan) if _meal_key(s.get("meal_type") or s.get("label") or "") == target]
    return matches[0] if len(matches) == 1 else None

def _context_plan(state, context):
    pid=(context or {}).get('meal_plan_id') or (context or {}).get('plan_id')
    if pid is None:return None
    cached=next((p for p in le.registry(state) if str(le.plan_id(p))==str(pid)),None)
    if cached is not None and str(state.get('_request_context_plan_id'))==str(pid):return cached
    actual=bc.get_meal_plan(pid)
    if str(le.plan_id(actual))!=str(pid):raise ValueError('卡片方案 ID 与后端返回不一致')
    le.remember(state,actual)
    state['_request_context_plan_id']=str(pid)
    return actual

def _operation_plan(state,message,context):
    card=_context_plan(state,context)
    if card is not None:return card
    plans=le.registry(state);indices=tr.plan_indices(message or '')
    if indices:
        if len(indices)!=1 or not 1<=indices[0]<=len(plans):raise ValueError(f'当前对话只有{len(plans)}份方案，请选择已有方案')
        state['current_plan']=plans[indices[0]-1];state['active_plan_id']=le.plan_id(plans[indices[0]-1])
        return plans[indices[0]-1]
    if len(plans)==1:return plans[0]
    if not plans:return None
    raise ValueError('当前有多份方案，请说明方案编号，或使用对应方案卡片操作')

def _operation_slot(plan,label,context):
    sid=(context or {}).get('meal_slot_id') or (context or {}).get('slot_id')
    if sid is not None:
        return next((s for s in _iter_slots(plan) if str(s.get('meal_slot_id') or s.get('slot_id'))==str(sid)),None)
    return _find_slot(plan,label)


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

# 规则引擎内部依据码 → 面向用户的中文表述（喂给 LLM 前先翻译，避免把原始码念给用户）。
REASON_CODE_ZH = {
    "staple_anchored": "主食打底",
    "veg_plus_protein": "蔬菜与蛋白并行",
    "low_oil_method": "蒸/拌为主、用油少",
    "low_salt": "低盐",
    "micro_coverage_high": "微量覆盖较好",
    "micro_balance_adjusted": "已做跨日微量平衡",
    "oil_salt_tightened": "油盐按收紧标准控制",
    "partial_data": "部分营养数据待核查",
}

# 7 种关键微量的中文名（micro_estimate 的键是 nutrient_id，转成中文再喂给 LLM）。
_MICRO_NAME_ZH = {
    "calcium": "钙", "iron": "铁", "zinc": "锌",
    "vitamin_a": "维生素A", "vitamin_b1": "维生素B1",
    "vitamin_b2": "维生素B2", "vitamin_c": "维生素C",
}


def _source_footer() -> str:
    """确定性来源页脚：数值口径来自固定参考（食物成分表 / 膳食指南 / DRIs），不靠 LLM 编造。"""
    names = " · ".join(s["title"] for s in blocks.SOURCES)
    return f"\n\n> 📚 数值口径来源：{names}"


def _explain_material(plan: dict) -> dict:
    """从当前方案抽取「为什么这样搭」的解释素材（只取后端/规则引擎给的数据，不自行计算）。"""
    meals = []
    for s in plan.get("slots", []):
        picked = s.get("selected_candidate") or (s.get("candidates") or [None])[0]
        if not picked:
            continue
        macro = picked.get("macro_estimate") or {}
        micro = picked.get("micro_estimate") or {}
        meals.append({
            "餐次": s.get("meal_type"),
            "日期": s.get("slot_date"),
            "本餐目标能量_kcal": (s.get("target_macro") or {}).get("kcal"),
            "菜": [f"{d.get('name', '')}（{d.get('portion_text', '')}）" for d in picked.get("dishes", [])],
            "能量_kcal": macro.get("kcal"),
            "蛋白_g": macro.get("protein_g"),
            "脂肪_g": macro.get("fat_g"),
            "碳水_g": macro.get("carb_g"),
            "膳食纤维_g": macro.get("fiber_g"),
            "微量": {_MICRO_NAME_ZH.get(k, k): v for k, v in micro.items()},
            "搭配说明": picked.get("why_text"),
            "搭配依据": [REASON_CODE_ZH.get(c, c) for c in picked.get("reason_codes", [])],
            "进食顺序建议": picked.get("eating_order_advice"),
        })
    return {
        "全天目标能量_kcal": plan.get("goal_energy_kcal"),
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
        target = (s.get("target_macro") or {}).get("kcal")
        target_txt = f"，本餐目标 {target} kcal" if target is not None else "，本餐目标未知"
        flags = (picked or {}).get("reason_codes") or []
        warnings = [label for code, label in (
            ("macro_range_relaxed", "营养近似结果"),
            ("oil_salt_unknown", "油盐数据不完整"),
            ("allergen_unverified", "过敏原未核查"),
        ) if code in flags]
        warning_txt = "；" + "、".join(warnings) if warnings else ""
        if names:
            lines.append(f"{s.get('slot_date') or ''} {meal}：{names}（{kcal_txt}{target_txt}{warning_txt}）")
    if len(slots) > limit:
        lines.append(f"……（共 {len(slots)} 餐，完整内容见卡片）")
    if not lines:
        lines.append("（方案内容见卡片）")
    return "\n".join(lines)


def _norm_date(s: str) -> str | None:
    """把 LLM 可能返回的日期串统一成 ISO（YYYY-MM-DD / YYYY年M月D日 / YYYY/M/D），失败返回 None。"""
    s = str(s).strip().replace("/", "-")
    m = re.match(r"(\d{4})[年\-](\d{1,2})[月\-](\d{1,2})日?", s)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
    except ValueError:
        return None


def _resolve_gen_params(kind: str, intent: dict) -> dict:
    """意图 → 生成请求的 start_date / end_date / meal_types（英文口径）+ scope_label。

    生成粒度不再限于「day/week/meal」三档：plan_custom 由 LLM 抽好的日期区间与餐次子集决定，
    plan_day/week/meal 仍走固定快捷路径（无 LLM 或抽不到时回退「今天三餐」）。
    """
    today = date.today()
    today_iso = today.isoformat()
    mt_map = {"早餐": "breakfast", "午餐": "lunch", "晚餐": "dinner"}
    all_meals = ["breakfast", "lunch", "dinner"]

    if kind == "plan_custom":
        start = _norm_date(intent.get("start_date") or "") or today_iso
        end = _norm_date(intent.get("end_date") or "") or start
        if end < start:
            start, end = end, start
        meals = [mt_map.get(str(x), x) for x in (intent.get("meal_types") or [])]
        meals = [x for x in meals if x in all_meals] or all_meals
        label = f"{start} ~ {end}" if start != end else start
        return {"start_date": start, "end_date": end, "meal_types": meals, "scope_label": label}

    if kind == "plan_week":
        return {"start_date": today_iso, "end_date": (today + timedelta(days=6)).isoformat(),
                "meal_types": all_meals, "scope_label": "接下来 7 天"}

    if kind == "plan_meal":
        mt = mt_map.get(intent.get("meal_type", ""), "lunch")
        return {"start_date": today_iso, "end_date": today_iso, "meal_types": [mt], "scope_label": "一餐"}

    # plan_day（默认）
    return {"start_date": today_iso, "end_date": today_iso, "meal_types": all_meals, "scope_label": "今天"}


# ================================================================ ③ tool-calling 编排

_MT_ZH2EN = {"早餐": "breakfast", "午餐": "lunch", "晚餐": "dinner"}
_ALL_MEALS = ["breakfast", "lunch", "dinner"]

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "generate_plan",
            "description": "为用户生成配餐方案。按日期区间与餐次生成，可带硬排除食材与软偏好（清淡/少油等）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "开始日期 YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "结束日期 YYYY-MM-DD（单日与 start_date 相同）"},
                    "meal_types": {"type": "array", "items": {"type": "string", "enum": ["早餐", "午餐", "晚餐"]}, "description": "要生成的餐次，默认全部"},
                    "exclude_ingredients": {"type": "array", "items": {"type": "string"}, "description": "硬排除的食材名（如「牛肉」）"},
                    "soft_avoid": {"type": "array", "items": {"type": "string"}, "description": "软偏好、尽量避开（如「油炸」「高油」）"},
                },
                "required": ["start_date", "end_date", "meal_types"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_clarification",
            "description": "用户需求含糊、缺少必要信息（没说几天/哪几餐/有歧义）时追问用户澄清。",
            "parameters": {
                "type": "object",
                "properties": {"question": {"type": "string", "description": "要问用户的问题"}},
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "swap_candidate",
            "description": "调整已有方案某一餐的候选（如「晚餐清淡点」「午餐不要牛肉」）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "meal_type": {"type": "string", "enum": ["早餐", "午餐", "晚餐"]},
                    "prefer": {"type": "string", "description": "调整意图，如「清淡」「不要牛肉」"},
                },
                "required": ["meal_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_shopping_list",
            "description": "获取当前方案的食材清单（需方案已确认）。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


_TOOLS.extend(le.TOOLS)

def _profile_brief(profile: dict) -> str:
    if not profile:
        return "用户档案：尚未建档。用户要求配餐时，应引导其先提供身体信息。"
    extras = profile.get("extras") or {}
    return (
        f"用户档案：性别{profile.get('gender') or '未知'}、年龄{profile.get('age')}、"
        f"身高{profile.get('height_cm')}cm、体重{profile.get('weight_kg')}kg、"
        f"目标{profile.get('goal_code') or 'maintain'}、过敏{profile.get('allergies') or '无'}、"
        f"忌口{profile.get('taboos') or '无'}、疾病{list((profile.get('conditions') or {}).keys()) or '无'}、"
        f"厨具{list(extras.get('cookware') or []) or '未填'}。"
    )


def _agent_system(profile: dict) -> str:
    return (
        SYSTEM_INSTRUCTION
        + "\n\n你是「膳宝」的决策编排器，可以调用工具来完成动作。\n"
        + _profile_brief(profile) + "\n"
        + f"今天是 {date.today().isoformat()}。\n"
        + "可用工具：generate_plan（生成配餐方案）、ask_clarification（需求含糊时追问）、"
          "swap_candidate（仅切换已有候选）、regenerate_slot（重生成单餐）、replace_dish（替换单菜）、get_shopping_list（查食材清单）。\n"
        + "局部修改必须使用对应工具，按用户明确指定的方案序号、日期和餐次定位，禁止擅自生成整份方案或确认；工具失败后停止，不得重试写操作或宣称成功。\n"
        + "规则：① 用户一次说多件事（如「排三天午餐顺便列清单」）就按顺序调用多个工具，最后统一回复；"
          "② 需要行动先调用工具，别凭空捏造方案内容；③ 数值只引用工具返回，绝不自行计算；"
          "④ 需求含糊（没说几天/哪几餐/有歧义）先调 ask_clarification，别擅自假设；"
          "⑤ 最终回复面向用户、结论先行、简洁自然，不要出现「工具」「调用」等内部字眼。"
    )


# 清淡/少油 → 软偏好关键词（匹配菜名里的高油做法，引擎按子串命中扣分降权）
_PREF_SOFT_AVOID = ["快炒", "炒", "红烧", "油炸", "炸", "煎", "干锅", "油焖", "糖醋", "回锅"]


def _extract_preferences(message: str) -> dict:
    """从用户消息确定性抽取「不要X→硬排除 / 清淡少油→软偏好」，作为 LLM 抽取的兜底。"""
    exclude: list[str] = []
    soft_avoid: list[str] = []
    if not message:
        return {"exclude": exclude, "soft_avoid": soft_avoid}
    for m in re.finditer(r"(?:不要|别吃|不吃|不想吃|避开|去掉|忌(?!口))([一-龥A-Za-z]{1,6})", message):
        word = m.group(1)
        if word and word not in exclude:
            exclude.append(word)
    if re.search(r"清淡|少油|低油|少放油|不油", message):
        for k in _PREF_SOFT_AVOID:
            if k not in soft_avoid:
                soft_avoid.append(k)
    return {"exclude": exclude, "soft_avoid": soft_avoid}


def _pick_swap_candidate(slot: dict, prefer: str) -> str | None:
    """从该餐候选里挑一个「要换成」的目标：默认下一个；带 prefer 时按语义挑。"""
    cands = slot.get("candidates") or []
    picked_id = slot.get("selected_candidate_id") or (slot.get("selected_candidate") or {}).get("candidate_id")
    others = [c for c in cands if str(c.get("candidate_id")) != str(picked_id)]
    if not others:
        return None
    if prefer:
        # ① 换成X → 优先含 X 的候选
        m = re.search(r"换成([一-龥A-Za-z]{1,6})", prefer)
        if m:
            word = m.group(1)
            hit = [c for c in others if word in _candidate_name(c)]
            if hit:
                others = hit
        # ② 不要X → 排除含 X 的候选
        m = re.search(r"(?:不要|别吃|不吃|不想吃|避开|去掉)([一-龥A-Za-z]{1,6})", prefer)
        if m:
            word = m.group(1)
            keep = [c for c in others if word not in _candidate_name(c)]
            if keep:
                others = keep
        # ③ 清淡/少油 → 用油最低优先
        if re.search(r"清淡|少油|太油|油腻|低油", prefer):
            def _oil(c):
                o = (c.get("oil_salt_estimate") or {}).get("oil_g")
                return o if o is not None else 9999.0
            others = sorted(others, key=_oil)
    return (others[0] or {}).get("candidate_id")


def _tool_exec(name: str, args: dict, ctx: dict, on_status=None) -> dict:
    """执行一个工具，返回 {summary, blocks, terminal, reply}。"""
    user_id = ctx["user_id"]
    st = ctx["state"]

    if name in ("regenerate_slot", "replace_dish"):
        if ctx.get("local_edit_attempted"):
            return {"terminal":True,"reply":"本轮已尝试局部修改，请检查结果后再提出下一项修改。"}
        ctx["local_edit_attempted"] = True
        try:
            updated, reply = le.execute(bc,st,name,args,ctx.get("message", ""))
            return {"terminal":True,"reply":reply,"blocks":[blocks.meal_card_block(updated)]}
        except ValueError as exc:
            return {"terminal":True,"reply":str(exc),"blocks":[]}
        except Exception as exc:
            return {"terminal":True,"reply":f"局部修改未获成功确认：{exc}。请刷新方案核对状态。","blocks":[]}

    if name == "generate_plan":
        if ctx.get("local_edit_only"):
            return {"terminal":True,"reply":"你指定的是局部修改，请明确目标餐位或菜式，我不会重新生成整份方案。"}
        if ctx["profile"] is None:
            return {"summary": "用户档案未建立，无法配餐。需先引导用户提供性别、年龄、身高体重、目标和过敏。"}
        meals = [_MT_ZH2EN.get(str(x), x) for x in (args.get("meal_types") or [])]
        meals = [x for x in meals if x in _ALL_MEALS] or _ALL_MEALS
        start = (args.get("start_date") or "").strip() or date.today().isoformat()
        end = (args.get("end_date") or "").strip() or start
        # ② 软偏好：LLM 抽的 + 确定性抽取兜底（「不要牛肉→exclude」「清淡→soft_avoid」）
        pref = _extract_preferences(ctx.get("message", ""))
        exclude = list(args.get("exclude_ingredients") or [])
        exclude += [x for x in pref["exclude"] if x not in exclude]
        soft = list(args.get("soft_avoid") or [])
        soft += [x for x in pref["soft_avoid"] if x not in soft]
        if on_status:
            on_status("正在生成配餐方案")
        plan = bc.generate_meal_plan(
            user_id=user_id, start_date=start, end_date=end, meal_types=meals,
            exclude_ingredients=exclude or None,
            soft_avoid=soft or None,
        )
        st.pop(rf.KEY, None)
        le.remember(st,plan)
        ctx["generated"] = True
        ctx.setdefault('generated_ids',[]).append(str(le.plan_id(plan)))
        return {"summary": f"已生成第{len(le.registry(st))}份方案（{start} ~ {end}）：\n{_plan_brief(plan)}",
                "blocks": [blocks.meal_card_block(plan)]}

    if name == "ask_clarification":
        q = (args.get("question") or "").strip() or "能再具体一点吗？"
        return {"terminal": True, "reply": q, "blocks": []}

    if name == "swap_candidate":
        if ctx.get("local_edit_only"):
            return {"terminal":True,"reply":"请明确是重新生成一餐还是替换一道菜。"}
        try:plan=_operation_plan(st,ctx.get('message',''),ctx.get('context'))
        except ValueError as exc:return {"terminal":True,"reply":str(exc)}
        if not plan:
            return {"summary": "还没有待调整的方案。"}
        meal_type = args.get("meal_type") or "午餐"
        slot = _operation_slot(plan,meal_type,ctx.get('context'))
        if not slot:
            return {"summary": "没找到对应的餐位。"}
        if on_status:
            on_status("正在调整候选")
        target_id = _pick_swap_candidate(slot, (args.get("prefer") or "").strip())
        meal_plan_id = plan.get("meal_plan_id") or plan.get("plan_id")
        bc.swap_candidate(
            meal_plan_id=meal_plan_id,
            meal_slot_id=slot.get("meal_slot_id") or slot.get("slot_id"),
            candidate_id=target_id,
        )
        updated = bc.get_meal_plan(meal_plan_id)
        le.remember(st,updated)
        new_slot = _find_slot(updated, meal_type)
        dish_text = _slot_dish_text(new_slot) if new_slot else "新候选"
        return {"summary": f"已把「{meal_type}」调整为：{dish_text}",
                "blocks": [blocks.meal_card_block(updated)]}

    if name == "get_shopping_list":
        plan = st.get("current_plan")
        if not plan or plan.get("status") != "fixed":
            return {"summary": "方案还没确认，暂时没有食材清单，需先确认方案。"}
        return {"summary": "食材清单已按类别整理好，可打开右侧工具栏「食材清单」面板查看、边买边勾。"}

    return {"summary": f"未知工具：{name}"}


def _no_llm_fallback(user_id: str, profile: dict, message: str, state: dict) -> dict:
    """无 LLM key 时的确定性兜底：只支持「一餐/一天/一周」排餐，其余给固定提示。"""
    if profile is None:
        return {"text": "还没有你的档案。可以先告诉我：性别、年龄、身高体重、目标和过敏，我建档后马上配餐。", "blocks": []}
    m = message.strip()
    if re.search(r"一周|七天|7天", m):
        kind = "plan_week"
    elif re.search(r"午餐|晚餐|早餐", m) and not re.search(r"三餐|一日", m):
        kind = "plan_meal"
    elif re.search(r"三餐|一日三餐|今天|明天|排|生成|推荐", m):
        kind = "plan_day"
    else:
        return {"text": "没有可用的语言模型，我暂时只能按「一餐/一天/一周」确定性排餐。", "blocks": []}
    gp = _resolve_gen_params(kind, {"meal_type": next((l for l in ("早餐", "午餐", "晚餐") if l in m), "午餐")})
    explicit=tr.generation_scope(m)
    if explicit:gp['start_date'],gp['end_date']=explicit
    mentioned=[en for zh,en in _MT_ZH2EN.items() if zh in m]
    if '三餐' in m:mentioned=list(_ALL_MEALS)
    if mentioned:gp['meal_types']=list(dict.fromkeys(mentioned))
    try:
        plan = bc.generate_meal_plan(
            user_id=user_id, start_date=gp["start_date"], end_date=gp["end_date"], meal_types=gp["meal_types"])
        le.remember(state,plan)
    except Exception as e:
        return {"text": f"方案没排出来：{e}", "blocks": []}
    return {"text": f"已生成方案{plan.get('display_index')}（{gp['start_date']} 至 {gp['end_date']}，离线兜底模式）。",
            "blocks": [blocks.meal_card_block(plan)]}


def _agent_loop(user_id: str, profile: dict, message: str, history: list | None,
                on_status=None, state=None, context=None) -> dict:
    """LLM 工具编排循环：LLM 决定调哪些工具、传什么参、要不要追问、要不要多步。"""
    client = _llm()
    if client is None:
        return _no_llm_fallback(user_id, profile, message, state)

    ctx = {"user_id": user_id, "profile": profile, "state": state, "message": message,"context":context or {},
           "local_edit_only": bool(re.search(r"重新(?:安排|生成|排)|重排|换掉|换成|替换.*(?:菜|肉|鱼|餐)|其他(?:不变|保留)|只换",message)) and bool(le.registry(state))}
    plan_list = [{"plan_index":i,"meal_plan_id":le.plan_id(p),"start_date":p.get("start_date"),"end_date":p.get("end_date"),
                  "slots":[{"date":s.get("slot_date"),"meal":s.get("meal_type"),"dishes":_slot_dish_text(s)} for s in _iter_slots(p)]}
                 for i,p in enumerate(le.registry(ctx["state"]),1)]
    messages: list[dict] = [{"role": "system", "content": _agent_system(profile) + "\n已有方案（只作定位）：" + json.dumps(plan_list,ensure_ascii=False)}]
    for h in history or []:
        role, content = h.get("role"), h.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": str(content)})
    messages.append({"role": "user", "content": message})

    collected_blocks: list[dict] = []
    summaries: list[str] = []
    terminal_reply: str | None = None
    fallback_text = ""

    for _ in range(6):
        try:
            resp = client.chat.completions.create(
                model=config.DEEPSEEK_MODEL, messages=messages, tools=_TOOLS, temperature=0,
            )
        except Exception:
            break
        msg = resp.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None)
        if not tool_calls:
            fallback_text = (msg.content or "").strip()
            break
        messages.append({
            "role": "assistant",
            "content": getattr(msg, "content", None),
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in tool_calls
            ],
        })
        stop = False
        for tc in tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except Exception:
                args = {}
            try:
                result = _tool_exec(tc.function.name, args, ctx, on_status)
            except Exception as exc:
                result = {"terminal":True,"reply":f"操作未获成功确认：{exc}。请刷新后核对状态。"}
            if result.get("blocks"):
                collected_blocks += result["blocks"]
            if result.get("summary"):
                summaries.append(f"[{tc.function.name}] {result['summary']}")
            if result.get("terminal"):
                terminal_reply = result.get("reply")
                stop = True
                break
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result.get("summary", "")})
        if stop:
            break

    # Do not let free-form narration renumber plans or conflate plan dates.
    if ctx.get("generated"):
        ids=set(ctx.get('generated_ids') or [])
        generated_text = "本轮已生成以下方案：\n" + "\n".join(
            rf.plan_label(p, i) for i,p in enumerate(le.registry(ctx["state"]),1) if str(le.plan_id(p)) in ids
        )
        if terminal_reply:
            generated_text += "\n" + terminal_reply
        return {"text": generated_text, "blocks": collected_blocks}

    # 追问：直接把问题返回给用户
    if terminal_reply is not None:
        return {"text": terminal_reply, "blocks": collected_blocks}

    # 有工具动作：把执行结果喂给叙事层，生成面向用户的正文（真流式）
    if summaries:
        fallback = "\n".join(summaries)
        return {"narration": _narrate(message, "\n".join(summaries), fallback, history),
                "blocks": collected_blocks}

    # 纯闲聊/未触发工具：直接回 LLM 文本
    return {"text": fallback_text or "这个我暂时答不好。可以让我排今天的三餐、换候选、或生成膳食报告。", "blocks": []}


def _run(user_id: str, message: str, history: list | None = None, on_status=None,
         *, state: dict, context: dict | None = None) -> dict:
    """执行一条用户消息，返回 {text|narration, blocks, ...}。
    history 为最近若干轮 user/assistant 文本；on_status(stage) 回调用于过程可见（真流式）。
    """
    def _st(s: str):
        if on_status:
            on_status(s)

    _st("正在理解你的需求")
    context=context or {};st=state
    # 每个请求只刷新一次结构化卡片目标；同一请求内后续动作复用该快照。
    st.pop('_request_context_plan_id', None)
    try:
        if (context.get('meal_plan_id') or context.get('plan_id')) is not None:_context_plan(st,context)
    except Exception as exc:
        return {"text":f"无法读取所选餐卡：{exc}","blocks":[]}
    # Explicit card actions are independent of pending natural-language edits.
    card_action = context.get("action")
    structured = card_action in ("swap_candidate", "choose_candidate", "confirm")
    if structured:
        if not context.get("meal_plan_id") or (card_action != "confirm" and not context.get("meal_slot_id")) or (card_action == "choose_candidate" and not context.get("candidate_id")):
            return {"text": "餐卡操作缺少必要标识，请刷新方案后重试。", "blocks": []}
        # Changing a card can invalidate a frozen pending edit preview.
        st.pop(rf.KEY, None)
    # A clear new-plan request owns the turn and cancels only unfinished task state.
    fresh=not structured and rf.is_new_plan_request(message)
    if fresh:st.pop(rf.KEY,None)
    flow = None if fresh or structured else rf.handle(bc, st, message)
    if flow is not None:
        return {"text": flow["text"], "blocks": [blocks.meal_card_block(p) for p in flow["updated_plans"]]}
    if not structured and re.search(r"重新(?:安排|生成|排)|重排|换掉|换成|替换.*(?:菜|肉|鱼|餐)|其他(?:不变|保留)|只换",message) and re.search(r"方案|第.*天|早餐|午餐|晚餐|换掉|换成|只换|其他",message):
        if not le.registry(st):
            return {"text":"当前对话没有可定位的待确认方案，请先生成方案或通过对应卡片选择。未进行修改。","blocks":[]}
        if _llm() is None:
            return {"text":"局部修改需要可用的语言模型来定位目标，请先恢复模型连接。未修改方案。","blocks":[]}
        return _agent_loop(user_id,_load_profile(user_id),message,history,on_status,st,context)
    intent = {"intent": card_action} if structured else classify(message)
    kind = intent.get("intent", "chat")
    _st("正在读取档案")
    profile = _load_profile(user_id)

    # ③ tool-calling 编排：配餐/调整/清单/闲聊/复合请求交给 LLM 工具循环；
    # 换/选/确认/取消等按钮短语 + 报告/问答/解释仍走下方既有分支。
    if kind in ("plan_day", "plan_week", "plan_meal", "plan_custom", "shopping_list", "chat"):
        return _agent_loop(user_id, profile, message, history, on_status,st,context)

    # 建档：用户描述自身指标
    if kind == "profile_build":
        _st("正在为你建档")
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
        # 建档后交给 LLM 工具循环排当天方案
        return _agent_loop(user_id, profile, message, history, on_status,st,context)

    # 换候选
    if kind == "swap_candidate":
        try:plan=_operation_plan(st,message,context)
        except ValueError as exc:return {"text":str(exc),"blocks":[]}
        if not plan:
            return {"text": "您还没有待确认的方案，要不要先生成今天的配餐？", "blocks": []}

        # 找到要换的是哪一餐
        slot = _operation_slot(plan,intent.get("meal_type") or "午餐",context)
        if not slot:
            return {"text": "没找到对应的餐位。", "blocks": []}

        _st("正在换候选")
        try:
            meal_plan_id = plan.get("meal_plan_id") or plan.get("plan_id")
            # 【修复】swap 接口只回部分结果（candidate + macro_delta），不携带完整 slots；
            # 这里调它只负责落库，完整方案再按 id 重新拉取，避免状态被部分结果覆盖。
            bc.swap_candidate(
                meal_plan_id=meal_plan_id,
                meal_slot_id=slot.get("meal_slot_id") or slot.get("slot_id"),
            )
            updated_plan = bc.get_meal_plan(meal_plan_id)
            le.remember(st,updated_plan)

            # 拿换好的新菜名 / 热量拼到文字里
            slot_id = slot.get("meal_slot_id") or slot.get("slot_id")
            new_slot = next((s for s in _iter_slots(updated_plan)
                             if str(s.get("meal_slot_id") or s.get("slot_id")) == str(slot_id)), None)
            if not new_slot or not new_slot.get("selected_candidate_id") or str(new_slot.get("selected_candidate_id")) == str(slot.get("selected_candidate_id")):
                return {"text": "未确认候选已切换，请刷新方案核对。", "blocks": []}
            new_dish_text = _slot_dish_text(new_slot)
            kcal_text = "热量待估"
            if new_slot:
                picked = new_slot.get("selected_candidate") or ((new_slot.get("candidates") or [None])[0])
                k = (picked or {}).get("macro_estimate", {}).get("kcal")
                if k is not None:
                    kcal_text = f"{k} kcal"

            fallback = f"换好啦！给你换成了 {new_dish_text}，这一顿 {kcal_text}。餐卡已更新，可以继续换，或点「确认方案」固定。"
            context = (
                f"动作：更换「{intent.get('meal_type') or '午餐'}」候选。\n"
                f"新候选：{new_dish_text}\n"
                f"该餐热量：{kcal_text}\n"
                "引导：卡片已更新，可继续换或确认。"
            )
            narration = _narrate(message, context, fallback, history)
            return {
                "narration": narration,
                # 【核心修改】只发前端认的 meal_card，删掉废弃的 anchor_block
                "blocks": [blocks.meal_card_block(updated_plan)]
            }
        except Exception as e:
            return {"text": f"换候选失败：{e}", "blocks": []}

    # 选用候选
    if kind == "choose_candidate":
        try:plan=_operation_plan(st,message,context)
        except ValueError as exc:return {"text":str(exc),"blocks":[]}
        if not plan:
            return {"text": "还没有方案。先生成一份吧。", "blocks": []}

        slot = _operation_slot(plan,intent.get("meal_type") or "午餐",context)
        if not slot:
            return {"text": "没找到这一餐。", "blocks": []}

        # 候选没有 name 字段（菜名在 dishes[].name）。用「菜名串完整出现在消息里」匹配，
        # 取最长命中（最具体）避免子集候选误命中（如单菜「米饭」被「米饭 + 清炒西兰花」抢走）。
        msg = intent.get("name") or ""
        wanted_id = (context or {}).get("candidate_id")
        target = next((c for c in slot.get("candidates") or []
                       if wanted_id is not None and str(c.get("candidate_id")) == str(wanted_id)), None)
        if wanted_id is not None and target is None:
            return {"text": "该候选已失效或不属于此餐位，请刷新方案。", "blocks": []}
        if target is None:
            for c in slot.get("candidates") or []:
                sig = _candidate_name(c)
                if sig and sig in msg:
                    if target is None or len(sig) > len(_candidate_name(target)):
                        target = c
        if not target:
            return {"text": "我没听清是哪个候选，可以把候选名称发我，或直接点候选卡片。",
                    "blocks": []}

        _st("正在选用候选")
        try:
            # 【核心修改】选用指定候选：多传 candidate_id；接口只落库，完整方案再按 id 拉取。
            meal_plan_id = plan.get("meal_plan_id") or plan.get("plan_id")
            bc.swap_candidate(
                meal_plan_id=meal_plan_id,
                meal_slot_id=slot.get("meal_slot_id") or slot.get("slot_id"),
                candidate_id=target.get("candidate_id", ""),
            )
            updated_plan = bc.get_meal_plan(meal_plan_id)
            le.remember(st,updated_plan)

            new_slot = _operation_slot(updated_plan, "", {"meal_slot_id": slot.get("meal_slot_id") or slot.get("slot_id")})
            if not new_slot or str(new_slot.get("selected_candidate_id")) != str(target.get("candidate_id")):
                return {"text": "未确认指定候选已选中，请刷新方案核对。", "blocks": []}
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
            narration = _narrate(message, context, fallback, history)
            return {
                "narration": narration,
                "blocks": [blocks.meal_card_block(updated_plan)]
            }
        except Exception as e:
            return {"text": f"选用失败：{e}", "blocks": []}

    # 取消（覆盖追问的否定回答）
    if kind == "cancel":
        return {"text": "好的，已保留旧方案，没有改动。", "blocks": []}

    # 确认 / 固定
    if kind == "confirm":
        try:plan=_operation_plan(st,message,context)
        except ValueError as exc:return {"text":str(exc),"blocks":[]}
        if not plan:
            return {"text": "现在还没有待确认的方案。我可以先按你的档案排今天的二餐，也可以排一周。", "blocks": []}

        replace = bool(intent.get("replace"))
        _st("正在确认方案")
        try:
            # 【核心修改】调后端接口，把状态改成 fixed 并落库；replace=True 时取代同期旧方案
            updated_plan = bc.fix_meal_plan(
                meal_plan_id=plan.get("meal_plan_id", ""), replace=replace
            )

            le.remember(st,updated_plan)
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
            narration = _narrate(message, context, fallback, history)
            return {
                "narration": narration,
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
            _st("正在生成膳食报告")
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
            narration = _narrate(message, context, fallback, history)
            return {
                "narration": narration,
                "blocks": [blocks.report_block(report)],
            }

        # 方案营养复盘（独立于膳食报告）：复盘当前方案
        plan = st.get("current_plan")

        if not plan:
            return {"text": "还没有可复盘的方案。先确认一份规划，再复盘这份方案的营养吧。", "blocks": []}

        # 后端方案主键是 meal_plan_id，方案级复盘 report_type=plan。
        plan_id = plan.get("meal_plan_id") or plan.get("plan_id", "")
        _st("正在复盘方案营养")

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
        narration = _narrate(message, context, fallback, history)
        return {
            "narration": narration,
            "blocks": [blocks.report_block(report)]
        }

    # 完整食谱 / 食材清单
    if kind == "recipe_detail":
        plan = st.get("current_plan")
        if not plan:
            return {"text": "还没有方案可以展开。要先排今天的三餐吗？", "blocks": []}
        fallback = "完整食谱卡片已送达，每道菜都有估量和热量。"
        context = "动作：展开完整食谱。引导：卡片已更新，每道菜含估量与热量。"
        _st("正在展开完整食谱")
        narration = _narrate(message, context, fallback, history)
        # 【修改】原本发 3 种废弃卡片，现在严格遵照清单要求改发 meal_card_block
        return {
            "narration": narration,
            "blocks": [blocks.meal_card_block(plan)]
        }

    # 反向营养 / 症状咨询
    if kind == "reverse_nutrition":
        _st("正在分析症状线索")
        try:
            r = bc.reverse_nutrition(message, 5)
            items = r.get("items", [])
            content = "；".join((it.get("content") or it.get("title") or "")[:120] for it in items[:3])
        except Exception:
            content = ""

        fallback = "单看症状无法下结论，建议先就医检查；饮食上注意均衡，可结合档案做针对性调整（仅供参考，不构成诊断）。"
        narration = _llm_reply(
            SYSTEM_INSTRUCTION + "\n针对症状咨询：给出可能的营养线索，措辞用「可能缺乏 / 建议关注」，不给定论，并注明仅供参考、不构成诊断、建议就医。" + _FMT,
            f"症状：{message}\n检索线索：{content or '无'}",
            fallback,
            history,
        )
        # 【修复 BUG-026】只有真的检索到线索才可标注「来自知识库」；检索为空时不得声称有文献来源
        # （可溯源/零编造铁律）。后缀作为确定性免责声明在流式后追加，正文由 LLM 组织。
        if content:
            suffix = "\n\n> 📚 以上营养线索来自知识库检索，仅供参考、不构成医学诊断，如有不适请及时就医。"
        else:
            suffix = "\n\n(以上为通用营养学常识，未检索到具体文献，仅供参考、不构成医学诊断，如有不适请及时就医。)"
        return {"narration": narration, "suffix": suffix, "blocks": []}

    # 知识问答
    # 解释「为什么这样搭」
    if kind == "explain":
        plan = st.get("current_plan")
        if not plan:
            return {
                "text": "现在还没有配好的方案，我暂时没有可解释的依据。先让我按你的档案排一餐或一日三餐，我再解释为什么这样搭。",
                "blocks": [],
            }
        material = _explain_material(plan)
        _st("正在整理搭配依据")
        fallback = "这套方案是结合你的档案与目标排的：主食打底保证供能，配菜兼顾蛋白质与蔬菜，具体依据如下…"
        narration = _llm_reply(
            SYSTEM_INSTRUCTION
            + "\n用下方方案数据解释「为什么这样搭」。先一句话给结论，再按骨架展开：\n"
              "### 好在哪\n- 3~4 条要点说清核心思路（蛋白怎么分散到三餐、蔬菜怎么安排、油盐/做法怎么控），每条 1 行；\n"
              "### 三餐怎么搭\n- 一张表格列三餐：餐次 | 能量 | 蛋白 | 核心菜；\n"
              "### 要注意\n- 只写真正影响决策的 1~2 条口径或风险（如「成品口径、热量是量级参考」「部分微量待核查」），没有就省略这一节；\n"
              "结尾一句自然的下一步引导。\n"
              "禁止：逐字复述餐卡；出现「后端/依据码/筛选逻辑」等内部细节；把「该项未提供」当内容硬凑；下「达标」结论（null≠0，单餐微量是贡献值、不是全天达标）。\n"
            + _FMT,
            f"用户问：{message}\n方案数据：{json.dumps(material, ensure_ascii=False)}",
            fallback,
            history,
        )
        # 确定性来源页脚：流式正文结束后追加，不依赖 LLM
        return {"narration": narration, "suffix": _source_footer(), "blocks": []}

    if kind == "rag_qa":
        _st("正在检索营养知识")
        try:
            r = bc.rag_query(message, 5)
            items = r.get("items", [])
            content = "；".join((it.get("content") or it.get("title") or "")[:160] for it in items[:3])
            sources = items
        except Exception:
            content = ""
            sources = []

        fallback = "这个问题建议结合权威膳食指南理解；如需针对性建议，我可以按你的档案给出更具体的方案。"
        narration = _llm_reply(
            SYSTEM_INSTRUCTION + "\n用检索到的资料回答，结论标注出处，注意双口径（生重/成品）与油盐话术。" + _FMT,
            f"问题：{message}\n检索资料：{content or '无'}",
            fallback,
            history,
        )
        # 【修改】停用 rag_sources 卡片，来源通过 LLM 文本呈现
        return {"narration": narration, "blocks": []}

    # 兜底（理论上不可达：classify 的 intent 均有分支，chat/plan_*/shopping_list 已路由到 _agent_loop）
    return {"text": "这个我暂时答不好。可以让我排今天的三餐、换候选、或生成膳食报告。", "blocks": []}


def run(user_id: str, message: str, history: list | None = None, on_status=None,
        *, conversation_id=None, context=None) -> dict:
    """Serialize mutations per authenticated conversation; different chats stay independent."""
    with cs.locked(user_id,conversation_id) as state:
        return _run(user_id,message,history,on_status,state=state,context=context or {})


def _week_start() -> str:
    d = date.today()
    return (d - timedelta(days=d.weekday())).isoformat()
