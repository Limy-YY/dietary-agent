# -*- coding: utf-8 -*-
"""Agent 编排核心：意图路由 + 确定性执行 + LLM 增值。

设计（对齐 v2.0「确定性计算与智能决策分离」）：
- 生成 / 换候选 / 确认 / 报告 等**结构化动作**走确定性路由（正则 + rule_engine / 后端 REST），
  LLM 不参与算数，只补自然语言；
- 知识问答 / 症状咨询 / 建档 等**自由输入**用 LLM 分类与组织语言，但数值结论仍来自工具。
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta

import backend_client as bc
import blocks
import config
import local_edits as le
import regenerate_flow as rf
import conversation_state as cs
import target_resolver as tr

logger = logging.getLogger(__name__)

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
    'reverse_nutrition（症状咨询，如口角炎/乏力/掉发）、'
    'capability（询问智能体能做什么/有哪些功能/使用帮助）、chat（闲聊）。\n'
    '注意：只有用户明确要求「生成/推荐/安排 菜单、三餐、食谱」时才归 plan_*；'
    '「一周/七天/7天」归 plan_week，「今天/明天一日三餐」归 plan_day，「推荐一餐」归 plan_meal，'
    '其余非标准范围（N 天、自定义日期、指定餐次子集）归 plan_custom；'
    '询问营养知识、食物功效、该怎么吃、忌口建议这类问题一律归 rag_qa；'
    '回顾/复盘一段时间或「吃得怎么样」这类话术归 report。\n'
    'JSON 字段：{"intent":"...", "meal_type":"早餐|午餐|晚餐|null", '
    '"scope":"week|month|plan|null", '
    '"start_date":"YYYY-MM-DD|null", "end_date":"YYYY-MM-DD|null", '
    '"meal_types":["早餐","午餐","晚餐"]|null, '
    '"profile":{"gender":"男|女|null","age":10~100|null,"height_cm":120~220|null,"weight_kg":30~200|null,'
    '"goal_code":"maintain|fat_loss|muscle_gain|glucose_control|digestive_health|null","allergies":[],"conditions":{},'
    '"activity_level":"久坐少动|轻度活动|中度活动|重度活动|null","name":""}}。'
    '用户没提到的 profile 字段一律填 null，绝不要填 0（0 会导致建档失败）。'
    'plan_custom 必须按下方规则填 start_date/end_date/meal_types，抽不出才留 null，绝不能编造日期：'
    '「今天」=今天日期，「明天」=明天，「三天/接下来三天」=从今天起连续 3 天，'
    '「下周一到周三」=下周对应具体日期（只排到周三就只排那几天），'
    '「只排午餐」=meal_types 只含「午餐」，「早晚餐」=["早餐","晚餐"]，没提餐次=["早餐","午餐","晚餐"]。'
    'report 需填 scope（月→month、周/最近/这段时间→week、自定义日期区间→custom、方案→plan），其余 intent 的 scope 为 null；'
    '仅 profile_build 需要填 profile，其余为 null。'
)


# 系统指令（回复生成时统一注入）：8 条共享铁律 + 4 处需求约束（FR-19/20/21/29）
SYSTEM_INSTRUCTION = (
    "你是「膳宝」，一位专业、温和、接地气的私人营养师：用「你」称呼用户，说话像真人营养师面对面沟通，"
    "有判断、有依据、不堆客套话、不念系统术语，先给清晰结论再自然解释原因。"
    "你负责个性化营养配餐、方案调整、膳食复盘与营养知识答疑。遵守以下铁律：\n"
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
    + "\n你要针对刚刚完成的动作向用户作自然回应，用自然段落即可，不要用标题、列表或表格。\n"
    "重要规则：\n"
    "- 严禁在开头或正文中照抄「方案1（2026-xx-xx 至…共N餐）」这类内部定位编号行，开头直接用自然语言切入；\n"
    "- 结构化卡片已经由前端单独渲染，不要逐菜报流水账，只需点出核心搭配亮点、能量量级与变化；\n"
    "- 如果是换候选、确认等小动作，用 1～2 句简洁确认即可；如果是刚生成配餐方案，请结合用户健康目标（减脂重结构与饱腹感、控糖重低升糖与碳水分配、增肌重优质蛋白）用专业营养师口吻讲清餐食优势与搭配依据，结尾自然引导单餐微调；\n"
    "- 所有数值只能引用「本轮结果」里给出的，不得自行计算或编造。"
)


_DATE_TOKEN_RE = re.compile(
    r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?|(\d{1,2})月(\d{1,2})[日号]"
)


def _parse_date_range(message: str) -> tuple[str, str] | None:
    """从消息里抽取两个日期（YYYY-MM-DD / YYYY年M月D日 / M月D日），返回 (start, end) ISO 串。

    无年份的「M月D日」按今年解析；当 end 早于 start 且 end 是无年份标记时，视为跨到次年
    （如「12月30日 到 1月2日」= 今年12-30 ~ 次年1-2），而不是简单交换成同年（BUG-042）。
    """
    tokens: list[date] = []
    yearless: list[bool] = []
    year = date.today().year
    for m in _DATE_TOKEN_RE.finditer(message):
        if m.group(1):
            tokens.append(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
            yearless.append(False)
        else:
            tokens.append(date(year, int(m.group(4)), int(m.group(5))))
            yearless.append(True)
    if len(tokens) < 2:
        return None
    start, end = tokens[0], tokens[1]
    if end < start:
        # 只有「end 无年份」且 (月,日) 更早时，才把 end 视为次年；其余情况仍按同年交换。
        if yearless[1] and (end.month, end.day) < (start.month, start.day):
            end = date(year + 1, end.month, end.day)
        else:
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
    """正则快路径：只认 canonical 话术（换/选/确认/固定/取消 + 明确范围词），其余交 LLM。

    收敛原则（P0）：正则当「高精度」分类器，不当「高召回」分类器——语义灰区一律返回 None 交 LLM。
    灰区例子（必须 None）：「推荐补钙食物」「贫血吃什么」「高血压食谱」「这周清淡点」「出差三天」。
    新增意图只加「明确动作词 / 明确范围词」，别加泛化词、别叠负向补丁。
    """
    m = message.strip()
    has = lambda pat: re.search(pat, m) is not None  # noqa: E731

    meal_alias = {
        "早餐": "早餐", "早饭": "早餐", "早上": "早餐",
        "午餐": "午餐", "午饭": "午餐", "中午": "午餐",
        "晚餐": "晚餐", "晚饭": "晚餐", "晚上": "晚餐",
    }

    if has(r"^(?:请问|你好|哈喽|嗨)?[，,！!\s]*(?:你|膳宝)?(?:能|可以|会)(?:做|干|帮我做)(?:什么|啥|哪些)|有哪些功能|功能介绍|怎么使用|能力范围"):
        return {"intent": "capability"}

    # ── 卡片按钮话术（换 / 选 / 确认·固定 / 取消）──
    if has(r"换一换|换一餐|换个候选|换个方案"):
        label = next((v for k, v in meal_alias.items() if k in m), None)
        # 只有「换一换 + 明确餐次」且不带局部替换/调整意图才走快捷；否则交 LLM 结合上下文
        if label and not has(r"换成|不要|不想吃|新鲜|重生成|重新|替换"):
            return {"intent": "swap_candidate", "meal_type": label}
        return None
    if has(r"选用|就用|选这个|选方案"):
        label = next((v for k, v in meal_alias.items() if k in m), None)
        if label:
            return {"intent": "choose_candidate", "meal_type": label, "name": m}
        return None
    if not has(r"(?:别|不要|不)固定") and (
            has(r"确认|固定|就这个|就它|就选|就这么|定了")
            or re.fullmatch(r"(?:替换|覆盖|取代)[。！!\s]*", m)
    ):
        return {"intent": "confirm", "replace": bool(re.fullmatch(r"(?:替换|覆盖|取代)[。！!\s]*", m))}
    if has(r"取消|算了|不用了|先不用"):
        return {"intent": "cancel"}

    # ── 结构化卡片动作（明确动作词）──
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

    # ── 明确范围词 → 配餐粒度（canonical 范围词；自定义/模糊范围先 defer）──
    if _is_custom_span(m):
        return None
    if has(r"一周|七天|7天|整周|一周食谱"):
        return {"intent": "plan_week"}
    # 配餐意图必须带「推荐/来」这类明确动作 + 餐次目标，不能只靠「吃什么/怎么配」这类词，
    # 否则「推荐补钙食物」「贫血吃什么」会被误判成配餐、跳出方案。
    if has(r"推荐(一餐|午餐|晚餐|早餐)|来一餐"):
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


def _profile_missing_fields(p: dict) -> list[str]:
    """建档必填项校验（与后端 ProfileUpsertRequest 约束对齐），返回缺失/非法字段名。

    铁律 7（needs_clarification 必须追问）：缺项就逐项追问，不静默用 0 硬填导致后端 422。
    """
    missing: list[str] = []
    if p.get("gender") not in ("男", "女"):
        missing.append("gender")
    try:
        if not (10 <= int(p.get("age")) <= 100):
            missing.append("age")
    except (TypeError, ValueError):
        missing.append("age")
    try:
        if not (120 <= float(p.get("height_cm")) <= 220):
            missing.append("height_cm")
    except (TypeError, ValueError):
        missing.append("height_cm")
    try:
        if not (30 <= float(p.get("weight_kg")) <= 200):
            missing.append("weight_kg")
    except (TypeError, ValueError):
        missing.append("weight_kg")
    if not str(p.get("goal_code") or "").strip():
        missing.append("goal_code")
    return missing


# ---------------------------------------------------------------- 方案动作

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
    # 固定冲突追问（替换/取消）不随身带方案 id：用上一轮「确认冲突」记住的目标方案兜底定位，
    # 避免多方案场景下裸话术「替换」定位失败。
    pid = state.get('_pending_confirm_plan_id')
    if pid is not None:
        for p in plans:
            if str(le.plan_id(p)) == str(pid):
                return p
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


def _rag_material(items: list[dict], *, limit: int = 5) -> tuple[str, str]:
    """为真实检索结果分配引用编号，并由程序组装来源列表。"""
    records: list[str] = []
    sources: list[str] = []
    for index, item in enumerate((items or [])[:limit], 1):
        title = str(item.get("title") or item.get("source") or f"资料 {index}").strip()
        content = str(item.get("content") or "").strip()
        source = str(item.get("source") or title).strip()
        source_id = str(item.get("source_id") or item.get("doc_id") or "").strip()
        source_url = str(item.get("source_url") or "").strip()
        records.append(
            f"[{index}] 标题：{title}\n内容：{content[:1200]}\n"
            f"来源：{source}\n来源编号：{source_id or '未提供'}"
        )
        label = source
        if source_id:
            label += f"（{source_id}）"
        sources.append(f"- [{index}] [{label}]({source_url})" if source_url else f"- [{index}] {label}")
    material = "\n\n".join(records)
    footer = "\n\n### 来源\n" + "\n".join(sources) if sources else ""
    return material, footer


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


def _plan_label_line(plan: dict) -> str:
    """方案定位行：带显示序号与日期/餐数（供叙事引用「方案 N」）。"""
    idx = plan.get("display_index")
    if idx:
        return rf.plan_label(plan, idx)
    slots = list(_iter_slots(plan))
    return f"已生成方案（{len(slots)} 餐）"


def _plan_coverage_feedback(plan: dict) -> str:
    """从方案抽取「覆盖度反馈」（reference_hints / data_quality_notes / why_summary），喂给审查闭环。

    只读后端已给的字段，不自行计算；覆盖度反馈是 §3.4 审查闭环的输入。
    """
    parts: list[str] = []
    why = plan.get("why_summary")
    hints = plan.get("reference_hints") or []
    notes = plan.get("data_quality_notes") or []
    if why:
        parts.append(f"搭配依据：{why}")
    if hints:
        parts.append("覆盖度提示：" + "；".join(str(h) for h in hints))
    if notes:
        parts.append("数据质量提示：" + "；".join(str(n) for n in notes))
    return "\n".join(parts)


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
            "description": "仅当用户明确要求「换一换 / 把某餐整顿换成另一套备选套餐」且已指明餐次、不带「不要X / 清淡少油」等偏好时调用（走候选内瞬时轮换）。若用户想去掉某道具体菜，改用 replace_dish；若用户要「换成 A+B 组合」或带忌口/清淡等偏好，改用 regenerate_slot；只说「换一换」未指明餐次则 ask_clarification。多日方案下未指明哪一天也先 ask_clarification。",
            "parameters": {
                "type": "object",
                "properties": {
                    "meal_type": {"type": "string", "enum": ["早餐", "午餐", "晚餐"],
                                  "description": "用户明确指定的餐次；未指定则留空"},
                    "prefer": {"type": "string", "description": "调整意图，如「清淡」「不要牛肉」"},
                    "day_index": {"type": "integer", "description": "多日方案中用户指定的第几天（从 1 开始）"},
                    "slot_date": {"type": "string", "description": "用户明确给出的日期 YYYY-MM-DD"},
                },
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
    {
        "type": "function",
        "function": {
            "name": "search_nutrition_knowledge",
            "description": "检索《中国居民膳食指南》《中国食物成分表》等权威营养知识库，解答食材营养价值、饮食宜忌、慢性病饮食建议与搭配原理。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "要检索的营养问题或食材关键词"},
                },
                "required": ["query"],
            },
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
          "swap_candidate（换一换 = 在生成时已产出的候选里换下一套，瞬时）、regenerate_slot（重生成单餐，可保留指定菜或落地排除/清淡等偏好）、"
          "replace_dish（替换单菜）、get_shopping_list（查食材清单）、search_nutrition_knowledge（检索权威营养知识库与食物成分）。\n"
        + "局部修改必须使用对应工具，按用户明确指定的方案序号、日期和餐次定位，禁止擅自生成整份方案或确认；工具失败后停止，不得重试写操作或宣称成功。\n"
        + "规则：① 用户一次说多件事（如「排三天午餐顺便列清单」「排三餐顺便查查痛风能不能吃菠菜」）就按顺序调用多个工具，最后统一回复；"
          "② 用户说「不想吃重复的」「换一换」等泛化请求且未指明具体餐次时，先对照已有方案找出跨餐重复菜，必须先调用 ask_clarification 追问用户想调整哪一餐（例如「午餐和晚餐都有「山药米饭」，你想换掉午餐的还是晚餐的？如果主食单换受限，也可以直接整餐重新生成」），禁止不问用户就擅自挑选餐次修改，也禁止诱导用户说「都换/一起换」（单轮仅支持修改一处）；"
          "③ 区分「局部替换」与「整餐重生成」：只有当用户明确指明要替换当前餐卡中【已有的某道具体菜】（如「把燕麦碗换成…」「不要西兰花蒸蛋」）时才调用 replace_dish；只要「换成/改成」前面是餐次名（如「早餐换成…」「晚餐改成…」），或用户表达「某餐我想吃 X」「X 加/和/配 Y」想指定整顿组合，或当前餐卡只有 1 道菜却想改成多道菜时，一律调用 regenerate_slot 整餐重生成，禁止调用 replace_dish；"
          "④ 需要行动先调用工具，别凭空捏造方案内容；⑤ 数值只引用工具返回，绝不自行计算；"
          "⑥ 若用户询问你的能力范围或能否检索营养资料，必须如实说明你具备个性化配餐、方案微调、权威营养知识库检索（《中国居民膳食指南》《中国食物成分表》等）及膳食报告分析能力，严禁声称「没有文献/知识检索功能」；"
          "⑦ 最终回复面向用户、结论先行、简洁自然，不要出现「工具」「调用」等内部字眼。"
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


# ================================================================ 规划意图（§3.3 富意图）

_PLAN_INTENT_SYSTEM = (
    "你是「膳宝」的配餐需求理解器。把用户的配餐诉求解析成结构化意图 JSON，只返回 JSON，不要多余文字。\n"
    "字段：\n"
    '  scope: {"start_date":"YYYY-MM-DD|null","end_date":"...","meal_types":["早","午","晚"]}；日期抽不出留 null，绝不能编造。\n'
    '  goal: 用户临时目标覆盖（maintain/fat_loss/muscle_gain/glucose_control/digestive_health），未提留 null。\n'
    '  hard_constraints: {"exclude_ingredients":[]} 硬排除食材（过敏/疾病忌口/「不要X」）。\n'
    '  soft_preferences: {"theme":"清淡中式","soft_avoid":["油炸"],"priority":["控糖 > 少油"]}。\n'
    '  day_overrides: [{"date":"YYYY-MM-DD","meal_types":["晚"],"hint":"晚餐从简（有应酬）"}] 单日特例。\n'
    '  user_explicits: {"want":["清蒸鱼"],"avoid":["香菜"]}。\n'
    '  needs_clarification: true/false；需求含糊或缺必要信息时 true，并给 clarify_question。\n'
    "规则：只做理解，不计算数值、不生成菜名；「不要/忌X」进 hard_constraints.exclude_ingredients 或 user_explicits.avoid；"
    "「清淡/少油/低盐」进 soft_preferences；「某天某餐」特例（如周三晚有应酬）进 day_overrides；"
    "「今天」=今天、「明天」=明天、「三天/接下来三天」=今天起连续 3 天、「下周」=下周一到周日。"
)


def _fallback_plan_intent(message: str) -> dict:
    """无 LLM / 解析失败时的确定性富意图兜底：scope 从消息抽，硬/软偏好走确定性抽取。"""
    scope: dict = {}
    explicit = tr.generation_scope(message)
    if explicit:
        scope["start_date"], scope["end_date"] = explicit
    meals: list[str] = []
    for zh, en in (("早餐", "早"), ("午餐", "午"), ("晚餐", "晚")):
        if zh in message or en in message:
            meals.append(en)
    if "三餐" in message or not meals:
        meals = ["早", "午", "晚"]
    scope["meal_types"] = list(dict.fromkeys(meals))
    pref = _extract_preferences(message)
    return {
        "scope": scope,
        "goal": None,
        "hard_constraints": {"exclude_ingredients": pref["exclude"]},
        "soft_preferences": {"soft_avoid": pref["soft_avoid"]},
        "day_overrides": [],
        "user_explicits": {},
        "needs_clarification": False,
    }


def _extract_plan_intent(message: str, profile: dict, history: list | None) -> dict:
    """LLM 产出规划意图 JSON（§3.3 富意图）。无 LLM / 出错回退确定性兜底。"""
    client = _llm()
    if client is None:
        return _fallback_plan_intent(message)
    system = _PLAN_INTENT_SYSTEM + f"\n今天是 {date.today().isoformat()}。\n用户档案：{_profile_brief(profile)}"
    messages: list[dict] = [{"role": "system", "content": system}]
    for h in history or []:
        role, content = h.get("role"), h.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": str(content)})
    messages.append({"role": "user", "content": message})
    try:
        resp = client.chat.completions.create(
            model=config.DEEPSEEK_MODEL,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0,
        )
        raw = resp.choices[0].message.content
        data = json.loads(raw)
        if not isinstance(data, dict):
            return _fallback_plan_intent(message)
        return data
    except Exception:
        return _fallback_plan_intent(message)


def _default_scope(kind: str | None) -> tuple[str, str]:
    """富意图没抽到日期时，用 classify 的 kind 兜底范围（plan_week=7 天，其余=今天单日）。"""
    today = date.today()
    if kind == "plan_week":
        return today.isoformat(), (today + timedelta(days=6)).isoformat()
    return today.isoformat(), today.isoformat()


def _map_plan_intent(rich: dict, message: str, kind: str | None = None) -> dict:
    """富意图 → 引擎参数（后端 GenerateRequest 当前支持的字段）。

    theme/priority/day_overrides 后端暂不支持、不强塞，仅映射 exclude/soft_avoid/日期餐次，
    其余富字段原样保留在返回里供审查闭环引用。日期抽不到时回退 kind 兜底范围。
    """
    today_iso = date.today().isoformat()
    mt_map = {"早": "breakfast", "午": "lunch", "晚": "dinner",
              "早餐": "breakfast", "午餐": "lunch", "晚餐": "dinner"}
    all_meals = ["breakfast", "lunch", "dinner"]

    scope = rich.get("scope") or {}
    start = _norm_date(scope.get("start_date") or "")
    end = _norm_date(scope.get("end_date") or "")
    if not start:
        start, end = _default_scope(kind)
    elif not end:
        end = start
    if end < start:
        start, end = end, start
    meals = [mt_map.get(str(x), x) for x in (scope.get("meal_types") or [])]
    meals = [x for x in meals if x in all_meals] or all_meals

    # 硬排除：hard_constraints.exclude_ingredients + user_explicits.avoid + 确定性「不要X」
    exclude = list((rich.get("hard_constraints") or {}).get("exclude_ingredients") or [])
    avoid = (rich.get("user_explicits") or {}).get("avoid") or []
    exclude += [x for x in avoid if x not in exclude]
    pref = _extract_preferences(message)
    exclude += [x for x in pref["exclude"] if x not in exclude]

    # 软偏好：soft_preferences.soft_avoid + theme 映射（清淡/少油 → 高油做法关键词）+ 确定性抽取
    soft = list((rich.get("soft_preferences") or {}).get("soft_avoid") or [])
    theme = str((rich.get("soft_preferences") or {}).get("theme") or "")
    if re.search(r"清淡|少油|低油", theme):
        for k in _PREF_SOFT_AVOID:
            if k not in soft:
                soft.append(k)
    soft += [x for x in pref["soft_avoid"] if x not in soft]

    return {
        "start_date": start,
        "end_date": end,
        "meal_types": meals,
        "exclude_ingredients": exclude,
        "soft_avoid": soft,
        # 富字段（后端暂不收，供审查闭环引用）
        "goal": rich.get("goal"),
        "theme": theme,
        "priority": (rich.get("soft_preferences") or {}).get("priority") or [],
        "day_overrides": rich.get("day_overrides") or [],
        "user_explicits": rich.get("user_explicits") or {},
    }


def _slim_intent(rich: dict) -> dict:
    """审查闭环用：只留「用户自己的约束」这类决策相关富字段，不 dump 内部 null。"""
    out: dict = {}
    for k in ("theme", "priority"):
        v = (rich.get("soft_preferences") or {}).get(k)
        if v:
            out[k] = v
    if rich.get("day_overrides"):
        out["day_overrides"] = rich["day_overrides"]
    if rich.get("user_explicits"):
        out["user_explicits"] = rich["user_explicits"]
    return out


def _wants_extra_tool(message: str) -> bool:
    """配餐消息里是否同时要清单/报告等额外动作（「排三天午餐顺便列清单」）。
    命中则交 _agent_loop 走多工具循环，不在快路径/富路径里丢掉附加动作。"""
    return bool(re.search(r"清单|买菜|采购|报告|复盘|食材", message))


# ================================================================ 配餐执行（C 快路径 + 富意图 + 审查闭环）

def _fast_generate(user_id, profile, message, kind, intent, history, on_status, st, context):
    """C 跳 LLM：canonical 范围词直连生成 + 一次叙事，跳过 _agent_loop 的 LLM 工具循环。

    仅当正则确定性命中 plan_day/week/meal 且已有档案时调用；软偏好用确定性 _extract_preferences 兜底。
    """
    gp = _resolve_gen_params(kind, intent)
    pref = _extract_preferences(message)
    if on_status:
        on_status("正在生成配餐方案")
    try:
        plan = bc.generate_meal_plan(
            user_id=user_id, start_date=gp["start_date"], end_date=gp["end_date"],
            meal_types=gp["meal_types"],
            exclude_ingredients=pref["exclude"] or None,
            soft_avoid=pref["soft_avoid"] or None,
        )
    except Exception as e:
        return {"text": f"方案没排出来：{e}", "blocks": []}
    st.pop(rf.KEY, None)
    le.remember(st, plan)
    # 修改 _fast_generate（约第 578 行）：去掉 _plan_label_line，补入档案与搭配依据
    fallback = "已为你排好配餐方案，各餐菜品与热量见下方餐卡，有哪一餐不合口味可以随时告诉我调整。"
    narrate_ctx = (
        f"{_profile_brief(profile)}\n"
        f"{_plan_brief(plan)}\n"
        f"{_plan_coverage_feedback(plan)}"
    )
    narration = _narrate(message, narrate_ctx, fallback, history)
    return {"narration": narration, "blocks": [blocks.meal_card_block(plan)]}


_REVIEW_SYSTEM = (
    _NARRATE_SYSTEM
    + "\n你要对刚生成的方案做一次审查再回复：\n"
    "- 只能引用下方「方案数据」里的数值与提示，不得自行计算或编造；\n"
    "- 先一句话给结论（这餐/这周怎么搭、热量量级），再自然点出关键信息并引导下一步；\n"
    "- 有数据质量提示（data_quality_notes）或覆盖度提示（reference_hints）时，"
      "用用户能懂的话转述（如「你上周蔬菜偏低，这周多加了绿叶菜」），不要念原始字段名；\n"
    "- 用户提过的偏好（清淡/少油/不要X/单日特例）要体现进解释，引用用户自己的约束；\n"
    "- 若存在无法满足的硬约束（过敏/疾病/宗教忌口），明确说出来并建议调整，不得装作已满足。\n"
    "语气参考范文（仅模仿口吻与结构，数值和菜名必须严格取自本轮「方案数据」）：\n"
    "「这份方案是按你减脂的目标搭配的，全天能量定在 1500 千卡左右，早中晚按三四三的能量比例分着吃。早餐选了燕麦牛奶粥，全谷物和乳制品就补上了；午餐杂粮饭加高蛋白的菜，蛋白质够、下午也不容易饿；晚餐特意安排的蒸拌做法，油和盐尽量少。减脂其实不用饿肚子，关键在于每顿结构齐全、蛋白和纤维补足，这样既不容易饿、血糖也稳。哪一餐不合口味，我可以单独给你调。」"
)


# 修改 _review_plan（约第 594 行）：去掉 _plan_label_line，补入 _profile_brief(profile)（注意同步给函数签名加上 profile 参数）
def _review_plan(message: str, rich: dict, plan: dict, history: list | None, profile: dict | None = None) -> dict:
    slim = _slim_intent(rich)
    context = _plan_brief(plan) + "\n" + _plan_coverage_feedback(plan)
    fallback = "已按你的需求排好配餐方案，详细搭配与热量见下方餐卡，需要微调哪一餐随时告诉我。"
    prompt = (
        f"用户消息：{message}\n\n"
        + (f"{_profile_brief(profile)}\n\n" if profile else "")
        + (f"用户约束：{json.dumps(slim, ensure_ascii=False)}\n\n" if slim else "")
        + f"方案数据：\n{context}"
    )
    return _llm_reply(_REVIEW_SYSTEM, prompt, fallback, history, temperature=0.6)


def _rich_generate(user_id, profile, message, kind, intent, history, on_status, st, context):
    """富意图配餐：LLM 出规划意图 → 映射引擎参数生成 → 审查覆盖度反馈出正文（§3.4）。"""
    if on_status:
        on_status("正在理解你的配餐需求")
    rich = _extract_plan_intent(message, profile, history)
    if rich.get("needs_clarification"):
        q = str(rich.get("clarify_question") or "").strip() or "能再说具体一点吗？"
        return {"text": q, "blocks": []}
    params = _map_plan_intent(rich, message, kind)
    if on_status:
        on_status("正在生成配餐方案")
    try:
        plan = bc.generate_meal_plan(
            user_id=user_id, start_date=params["start_date"], end_date=params["end_date"],
            meal_types=params["meal_types"],
            exclude_ingredients=params["exclude_ingredients"] or None,
            soft_avoid=params["soft_avoid"] or None,
        )
    except Exception as e:
        return {"text": f"方案没排出来：{e}", "blocks": []}
    st.pop(rf.KEY, None)
    le.remember(st, plan)
    if on_status:
        on_status("正在审查方案")
    return {"narration": _review_plan(message, rich, plan, history, profile),
            "blocks": [blocks.meal_card_block(plan)]}


def _tool_exec(name: str, args: dict, ctx: dict, on_status=None) -> dict:
    """执行一个工具，返回 {summary, blocks, terminal, reply}。"""
    user_id = ctx["user_id"]
    st = ctx["state"]

    if name in ("regenerate_slot", "replace_dish"):
        if ctx.get("local_edit_attempted"):
            return {"terminal": True, "reply": "本轮已尝试局部修改，请检查结果后再提出下一项修改。"}
        ctx["local_edit_attempted"] = True
        try:
            updated, reply = le.execute(bc, st, name, args, ctx.get("message", ""))
            narrate_ctx = (
                f"{reply}\n"
                "提示：请对照用户原话检查最终菜品。若用户点名的某道菜未出现在最终结果中，严禁含糊地说「没能排进」，"
                "必须用一句话向用户明确说明具体的饮食规则原因（按实际情况判断：1. 同属主食，单餐不能双碳水叠加；"
                "2. 餐次适配限制，如正餐肉菜/炒菜仅限午晚餐、不在早餐菜谱库中；3. 档案过敏忌口或单餐营养结构限制），"
                "再说明已替换为当前餐次更均衡的同类营养菜品；若完全符合则简洁确认即可。"
                "结尾只能引导当前餐次的后续操作，严禁编造「把菜挪到其他餐次」等不存在的功能。"
            )
            return {
                "terminal": True,
                "reply": reply,
                "narration": _narrate(ctx.get("message", ""), narrate_ctx, reply, ctx.get("history")),
                "blocks": [blocks.meal_card_block(updated)],
            }
        except ValueError as exc:
            raw_reply = str(exc)
            fail_ctx = (
                f"拦截原因：{raw_reply}\n"
                "提示：用户的局部修改请求未通过菜名或餐次定位校验，原方案保持不变。请结合对话历史中的当前方案，"
                "用一两句话自然向用户说明原因，并引导其指定当前餐卡中的具体菜名或餐次。"
            )
            return {
                "terminal": True,
                "reply": raw_reply,
                "narration": _narrate(ctx.get("message", ""), fail_ctx, raw_reply, ctx.get("history")),
                "blocks": [],
            }
        except Exception as exc:
            raw_reply = f"局部修改未获成功确认：{exc}。请刷新方案核对状态。"
            fail_ctx = (
                f"拦截原因：{exc}\n"
                "提示：本次局部修改未执行、原方案保留。请先核对当前餐卡的已有菜品：\n"
                "1. 若用户想换入的新菜【已经存在于当前餐卡中】（如本餐已有二米饭却还要把别的菜换成二米饭），直接自然告知「本餐已经包含「XX」了，同一顿不会重复排两份相同的菜」，严禁扯双碳水或建议用它替换自己；\n"
                "2. 若是两道不同的主食冲突，再说明「单餐不能同时搭配两种主食」；\n"
                "3. 若因替换后缺少蛋白/蔬菜导致结构失衡，再提示选择同类菜品。严禁输出「局部修改未成功确认」「请刷新方案核对状态」等系统报错腔。"
            )
            return {
                "terminal": True,
                "reply": raw_reply,
                "narration": _narrate(ctx.get("message", ""), fail_ctx, raw_reply, ctx.get("history")),
                "blocks": [],
            }

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
        try:plan=_operation_plan(st,ctx.get('message',''),ctx.get('context'))
        except ValueError as exc:return {"terminal":True,"reply":str(exc)}
        if not plan:
            return {"summary": "还没有待调整的方案。"}
        meal_type = (args.get("meal_type") or "").strip()
        if not meal_type:
            return {"summary": "未指明要调整哪一餐，请追问用户具体想调整早餐、午餐还是晚餐。"}
        # 卡片按钮路径带 meal_slot_id（_operation_slot）；自然语言走 le.resolve_slot 支持
        # day_index/slot_date，避免多日方案下 meal_type 命中多个餐位而定位失败（BUG-040）。
        slot = None
        if (ctx.get('context') or {}).get('meal_slot_id'):
            slot = _operation_slot(plan, meal_type, ctx.get('context'))
        else:
            try:
                slot = le.resolve_slot(plan, args)
            except ValueError as exc:
                return {"summary": str(exc)}
        if not slot:
            return {"summary": "没找到对应的餐位。"}
        if on_status:
            on_status("正在换候选")
        # 换一换 = 生成期已产出的候选内瞬时轮换（IMP-059 已把跨天多样性做进生成期，无需重跑引擎）。
        # 只有带「不要X / 清淡少油」等偏好时，才走 slot/regenerate（exclude/soft_avoid 只有它能落地）。
        prefer = (args.get("prefer") or "").strip()
        ex = _extract_preferences(prefer)
        meal_plan_id = plan.get("meal_plan_id") or plan.get("plan_id")
        if ex["exclude"] or ex["soft_avoid"]:
            bc.regenerate_slot(
                meal_plan_id=meal_plan_id,
                meal_slot_id=slot.get("meal_slot_id") or slot.get("slot_id"),
                expected_candidate_id=slot.get("selected_candidate_id"),
                exclude_ingredients=ex["exclude"],
                soft_avoid=ex["soft_avoid"],
            )
            updated = bc.get_meal_plan(meal_plan_id)
        else:
            updated = bc.swap_candidate(
                meal_plan_id=meal_plan_id,
                meal_slot_id=slot.get("meal_slot_id") or slot.get("slot_id"),
            )
        le.remember(st,updated)
        new_slot = _find_slot(updated, meal_type)
        dish_text = _slot_dish_text(new_slot) if new_slot else "新候选"
        return {"summary": f"已重新搭配「{meal_type}」：{dish_text}",
                "blocks": [blocks.meal_card_block(updated)]}

    if name == "get_shopping_list":
        plan = st.get("current_plan")
        if not plan or plan.get("status") != "fixed":
            return {"summary": "方案还没确认，暂时没有食材清单，需先确认方案。"}
        shopping = bc.get_shopping_list(le.plan_id(plan))
        return {
            "summary": "已根据最终确认方案生成食材清单。",
            "blocks": [blocks.shopping_list_block(shopping)],
        }

    if name == "search_nutrition_knowledge":
        q = (args.get("query") or ctx.get("message") or "").strip()
        if on_status:
            on_status("正在检索营养知识")
        try:
            r = bc.rag_query(q, 5)
            items = r.get("items", [])
            content, _ = _rag_material(items)
        except Exception:
            content = ""
        if not content:
            return {"summary": "知识库暂未检索到足够依据，请如实告知用户无法查证，严禁编造来源或数值。"}
        return {"summary": f"已检索到以下权威营养资料（回答时请引用出处，不得编造）：\n{content}"}

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

    ctx = {"user_id": user_id, "profile": profile, "state": state, "message": message, "history": history,"context": context or {},
           "local_edit_only": bool(
               re.search(r"重新(?:安排|生成|排)|重排|换成|替换.*(?:菜|肉|鱼|餐)|其他(?:不变|保留)|只换",
                         message)) and bool(le.registry(state)) and not rf.is_new_plan_request(message)}
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
    terminal_narration: dict | None = None
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
                terminal_narration = result.get("narration")
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
    if terminal_narration is not None:
        return {"narration": terminal_narration, "blocks": collected_blocks}
    if terminal_reply is not None:
        return {"text": terminal_reply, "blocks": collected_blocks}

    # 有工具动作：把执行结果喂给叙事层，生成面向用户的正文（真流式）
    if summaries:
        fallback = "\n".join(summaries)
        return {"narration": _narrate(message, "\n".join(summaries), fallback, history),
                "blocks": collected_blocks}

    # 纯闲聊/未触发工具：直接回 LLM 文本
    return {"text": fallback_text or "这个我暂时答不好。可以让我排今天的三餐、换候选、或生成膳食报告。", "blocks": []}


def _run_plan(user_id, profile, message, kind, intent, history, on_status, st, context):
    """配餐统一入口：canonical 范围词走快路径（C），其余走富意图 + 审查闭环（§3.3/3.4）。

    多工具请求（「排三天午餐顺便列清单」）仍交 _agent_loop 走工具循环，避免丢掉附加动作。
    """
    if _wants_extra_tool(message):
        return _agent_loop(user_id, profile, message, history, on_status, st, context)
    if _llm() is None:
        return _no_llm_fallback(user_id, profile, message, st)
    if profile is None:
        return _agent_loop(user_id, profile, message, history, on_status, st, context)
    # C 跳 LLM：正则确定性命中标准配餐（plan_day/week/meal）→ 直连生成 + 一次叙事
    reg = _regex_intent(message)
    if reg is not None and reg.get("intent") == kind:
        return _fast_generate(user_id, profile, message, kind, intent, history, on_status, st, context)
    # 富意图 + 审查闭环
    return _rich_generate(user_id, profile, message, kind, intent, history, on_status, st, context)


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
    # Explicit card actions are independent of pending natural-language edits.
    card_action = context.get("action")
    structured = card_action in ("swap_candidate", "choose_candidate", "confirm")
    # 结构化卡片动作（换一换/选用/确认）直接用上下文里的 id 调后端，无需先拉全量方案
    # （省一次 get_meal_plan 往返）；后端会兜底校验归属/状态/槽位/候选。
    # 只有非结构化请求（如自然语言后续 + 随身带 meal_plan_id）才预取目标方案。
    try:
        if not structured and (context.get('meal_plan_id') or context.get('plan_id')) is not None:
            _context_plan(st, context)
    except Exception as exc:
        return {"text": f"无法读取所选餐卡：{exc}", "blocks": []}
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
    if not structured and re.search(r"重新(?:安排|生成|排)|重排|换成|替换.*(?:菜|肉|鱼|餐)|其他(?:不变|保留)|只换",
                                    message) and re.search(r"方案|第.*天|早餐|午餐|晚餐|早上|中午|晚上|换成|只换|其他",
                                                           message):
        if not le.registry(st):
            return {"text":"当前对话没有可定位的待确认方案，请先生成方案或通过对应卡片选择。未进行修改。","blocks":[]}
        if _llm() is None:
            return {"text":"局部修改需要可用的语言模型来定位目标，请先恢复模型连接。未修改方案。","blocks":[]}
        return _agent_loop(user_id,_load_profile(user_id),message,history,on_status,st,context)
    intent = {"intent": card_action} if structured else classify(message)
    kind = intent.get("intent", "chat")
    # 卡片动作（换一换/选用/确认）无需档案，跳过 _load_profile 的 REST 往返（省一次 get_profile）。
    profile = None if structured else _load_profile(user_id)
    if not structured:
        _st("正在读取档案")

    # ③ tool-calling 编排：配餐走 _run_plan（快路径 / 富意图 + 审查闭环）；
    # 清单 / 闲聊 / 复合请求仍走 _agent_loop 工具循环；换/选/确认/取消等按钮短语 + 报告/问答/解释走下方既有分支。
    if kind in ("plan_day", "plan_week", "plan_meal", "plan_custom"):
        return _run_plan(user_id, profile, message, kind, intent, history, on_status, st, context)
    if kind in ("shopping_list", "chat"):
        return _agent_loop(user_id, profile, message, history, on_status, st, context)

    # 建档：用户描述自身指标
    if kind == "profile_build":
        _st("正在为你建档")
        p = intent.get("profile") or {}
        # 铁律 7：缺必填项逐项追问，不用 0 硬填导致后端 422 后静默吞掉（BUG-036）。
        missing = _profile_missing_fields(p)
        if missing:
            label = {"gender": "性别", "age": "年龄", "height_cm": "身高",
                     "weight_kg": "体重", "goal_code": "健康目标"}
            asks = "、".join(label.get(k, k) for k in missing)
            return {"text": f"建档还差这些信息：{asks}。补充后我再为你建档配餐。", "blocks": []}
        if p.get("name"):
            new_id = "u_" + re.sub(r"[^a-z0-9]", "", p["name"].lower()) or "u_" + date.today().strftime("%Y%m%d")
        else:
            new_id = user_id
        try:
            bc.upsert_profile(
                new_id,
                gender=p.get("gender"), age=p.get("age"), height_cm=p.get("height_cm"),
                weight_kg=p.get("weight_kg"), goal_code=p.get("goal_code"),
                allergies=p.get("allergies") or [],
                conditions=p.get("conditions") or {},
                activity_level=p.get("activity_level") or "久坐少动",
                extras={"name": p.get("name") or ""},
            )
            profile = _load_profile(new_id)
            user_id = new_id
        except Exception as exc:
            # 不再静默吞 422：记日志，下面按 profile 为空走「追问缺项」而非假装已建档（BUG-036）。
            logger.warning("对话建档失败 user=%s err=%s", user_id, exc)
        if profile is None:
            return {"text": "我还不太了解你的身体情况，可以告诉我性别、年龄、身高体重和目标吗？", "blocks": []}
        # 建档后交给 LLM 工具循环排当天方案
        return _agent_loop(user_id, profile, message, history, on_status,st,context)

    if kind == "capability":
        return {
            "text": (
                "我是你的私人膳食营养助手「膳宝」，目前可以帮你做这些事：\n"
                "- **个性化建档与配餐**：根据你的身体指标、健康目标（减脂/增肌/控糖/维持等）及过敏忌口，生成单餐、一日三餐、一周或指定日期的食谱方案；\n"
                "- **方案微调与搭配解析**：支持整餐重生成、单菜替换、备选套餐切换，并为你解释每顿饭的营养结构与搭配依据；\n"
                "- **营养知识检索问答**：基于《中国居民膳食指南》《中国食物成分表》等权威资料，解答食材营养、饮食宜忌与日常搭配问题；\n"
                "- **症状营养线索与膳食复盘**：针对常见不适提供饮食侧的营养参考线索，并在确认方案后生成周/月膳食分析报告与采购食材清单。\n\n"
                "需要注意：我提供的营养分析与线索仅作日常饮食参考，不能替代医院检查或医学诊断。"
            ),
            "blocks": [],
        }

    # 换候选
    if kind == "swap_candidate":
        # 结构化卡片动作（换一换按钮）：上下文已带 meal_plan_id / meal_slot_id，直接调后端，
        # 省掉 _context_plan 的 get_meal_plan 往返；后端 /candidate/swap 返回全量方案。
        if structured and context.get("meal_plan_id") and (context.get("meal_slot_id") or context.get("slot_id")):
            _st("正在换候选")
            try:
                updated_plan = bc.swap_candidate(
                    meal_plan_id=context.get("meal_plan_id"),
                    meal_slot_id=context.get("meal_slot_id") or context.get("slot_id"),
                )
                le.remember(st, updated_plan)
                sid = context.get("meal_slot_id") or context.get("slot_id")
                new_slot = next((s for s in _iter_slots(updated_plan)
                                 if str(s.get("meal_slot_id") or s.get("slot_id")) == str(sid)), None)
                if not new_slot or not new_slot.get("selected_candidate_id"):
                    return {"text": "未确认候选已切换，请刷新方案核对。", "blocks": []}
                new_dish_text = _slot_dish_text(new_slot)
                kcal_text = "热量待估"
                picked = new_slot.get("selected_candidate") or ((new_slot.get("candidates") or [None])[0])
                k = (picked or {}).get("macro_estimate", {}).get("kcal")
                if k is not None:
                    kcal_text = f"{k} kcal"
                fallback = f"换好啦！给你换成了 {new_dish_text}，这一顿 {kcal_text}。餐卡已更新，可以继续换，或点「确认方案」固定。"
                context_txt = (
                    f"动作：更换「{intent.get('meal_type') or '午餐'}」候选。\n"
                    f"新候选：{new_dish_text}\n"
                    f"该餐热量：{kcal_text}\n"
                    "引导：卡片已更新，可继续换或确认。"
                )
                narration = _narrate(message, context_txt, fallback, history)
                return {"narration": narration, "blocks": [blocks.meal_card_block(updated_plan)]}
            except Exception as e:
                return {"text": f"换候选失败：{e}", "blocks": []}

        # 自然语言路径：按意图定位方案/餐位。
        try:plan=_operation_plan(st,message,context)
        except ValueError as exc:return {"text":str(exc),"blocks":[]}
        if not plan:
            return {"text": "您还没有待确认的方案，要不要先生成今天的配餐？", "blocks": []}

        # 找到要换的是哪一餐
        slot = _operation_slot(plan,intent.get("meal_type") or "",context)
        if not slot:
            return {"text": "没找到对应的餐位。", "blocks": []}

        _st("正在换候选")
        try:
            meal_plan_id = plan.get("meal_plan_id") or plan.get("plan_id")
            old_dish_text = _slot_dish_text(slot)
            # 换一换 = 生成期已产出的候选内瞬时轮换（IMP-059 已把跨天多样性做进生成期，
            # 候选不再「原地打转」，无需重跑引擎）。/candidate/swap 直接返回全量方案，无需再重拉。
            updated_plan = bc.swap_candidate(
                meal_plan_id=meal_plan_id,
                meal_slot_id=slot.get("meal_slot_id") or slot.get("slot_id"),
            )
            le.remember(st,updated_plan)

            # 拿换好的新菜名 / 热量拼到文字里
            slot_id = slot.get("meal_slot_id") or slot.get("slot_id")
            new_slot = next((s for s in _iter_slots(updated_plan)
                             if str(s.get("meal_slot_id") or s.get("slot_id")) == str(slot_id)), None)
            if not new_slot or not new_slot.get("selected_candidate_id"):
                return {"text": "未确认候选已切换，请刷新方案核对。", "blocks": []}
            new_dish_text = _slot_dish_text(new_slot)
            if new_dish_text == old_dish_text:
                return {"text": "这一餐没能换出新搭配，请刷新方案核对，或换个餐位再试。", "blocks": []}
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
        wanted_id = context.get("candidate_id")
        meal_plan_id = context.get("meal_plan_id") or context.get("plan_id")
        meal_slot_id = context.get("meal_slot_id") or context.get("slot_id")

        # 结构化卡片动作：上下文已带全三件套 id，直接调后端（后端现在回全量方案），
        # 省掉「先 _context_plan 拉方案 + 换完再 get_meal_plan」两次往返。
        if wanted_id is not None and meal_plan_id and meal_slot_id:
            _st("正在选用候选")
            try:
                updated_plan = bc.swap_candidate(
                    meal_plan_id=meal_plan_id,
                    meal_slot_id=meal_slot_id,
                    candidate_id=wanted_id,
                )
                le.remember(st, updated_plan)
                new_slot = next((s for s in _iter_slots(updated_plan)
                                 if str(s.get("meal_slot_id") or s.get("slot_id")) == str(meal_slot_id)), None)
                if not new_slot or str(new_slot.get("selected_candidate_id")) != str(wanted_id):
                    return {"text": "未确认指定候选已选中，请刷新方案核对。", "blocks": []}
                picked = new_slot.get("selected_candidate") or {}
                kcal = (picked.get("macro_estimate") or {}).get("kcal")
                kcal_text = f"{kcal} kcal" if kcal is not None else "热量待估"
                name = " + ".join(str(d.get("name", "")) for d in (picked.get("dishes") or []))
                fallback = f"已选定 {name}，这一顿 {kcal_text}。"
                context_txt = (
                    f"动作：选定「{intent.get('meal_type') or '午餐'}」候选。\n"
                    f"选定菜品：{name}\n"
                    f"该餐热量：{kcal_text}\n"
                    "引导：卡片已更新，可继续调整或确认。"
                )
                narration = _narrate(message, context_txt, fallback, history)
                return {"narration": narration, "blocks": [blocks.meal_card_block(updated_plan)]}
            except Exception as e:
                return {"text": f"选用失败：{e}", "blocks": []}

        # 自然语言路径（未带 candidate_id，需按菜名匹配候选）：先定位方案/餐位。
        try:plan=_operation_plan(st,message,context)
        except ValueError as exc:return {"text":str(exc),"blocks":[]}
        if not plan:
            return {"text": "还没有方案。先生成一份吧。", "blocks": []}

        slot = _operation_slot(plan,intent.get("meal_type") or "",context)
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

        _st("正在选用候选")
        try:
            pid = plan.get("meal_plan_id") or plan.get("plan_id")
            bc.swap_candidate(
                meal_plan_id=pid,
                meal_slot_id=slot.get("meal_slot_id") or slot.get("slot_id"),
                candidate_id=target.get("candidate_id", ""),
            )
            updated_plan = bc.get_meal_plan(pid)
            le.remember(st,updated_plan)

            new_slot = _operation_slot(updated_plan, "", {"meal_slot_id": slot.get("meal_slot_id") or slot.get("slot_id")})
            if not new_slot or str(new_slot.get("selected_candidate_id")) != str(target.get("candidate_id")):
                return {"text": "未确认指定候选已选中，请刷新方案核对。", "blocks": []}
            kcal = (target.get("macro_estimate") or {}).get("kcal")
            kcal_text = f"{kcal} kcal" if kcal is not None else "热量待估"
            name = _candidate_name(target)
            fallback = f"已选定 {name}，这一顿 {kcal_text}。"
            context_txt = (
                f"动作：选定「{intent.get('meal_type') or '午餐'}」候选。\n"
                f"选定菜品：{name}\n"
                f"该餐热量：{kcal_text}\n"
                "引导：卡片已更新，可继续调整或确认。"
            )
            narration = _narrate(message, context_txt, fallback, history)
            return {
                "narration": narration,
                "blocks": [blocks.meal_card_block(updated_plan)]
            }
        except Exception as e:
            return {"text": f"选用失败：{e}", "blocks": []}

    # 取消（覆盖追问的否定回答）
    if kind == "cancel":
        st.pop("_pending_confirm_plan_id", None)
        return {"text": "好的，已保留旧方案，没有改动。", "blocks": []}

    # 确认 / 固定
    if kind == "confirm":
        # 结构化卡片动作（确认按钮）：上下文已带 meal_plan_id，直接调后端，省掉 get_meal_plan 往返。
        # 冲突（同期已有固定方案）时后端返回 2005，仍需返回 quick_actions 让用户二选一（替换/取消）。
        if structured and context.get("meal_plan_id"):
            _st("正在确认方案")
            try:
                updated_plan = bc.fix_meal_plan(
                    meal_plan_id=context.get("meal_plan_id"), replace=False
                )
                st.pop("_pending_confirm_plan_id", None)
                le.remember(st, updated_plan)
                st["plans"].insert(0, dict(updated_plan))
                fallback = "已确认，方案已生效。食材清单已按类别整理好，可在右侧「食材清单」查看。"
                context_txt = (
                    "动作：确认/固定当前方案。\n"
                    "是否取代同期的旧方案：否\n"
                    "营养分析：用户未请求。"
                )
                narration = _narrate(message, context_txt, fallback, history)
                return {
                    "narration": narration,
                    "blocks": [blocks.meal_card_block(updated_plan)],
                }
            except bc.BackendError as e:
                if getattr(e, "code", None) == 2005:
                    st["_pending_confirm_plan_id"] = context.get("meal_plan_id")
                    return {
                        "text": "这段时间已有固定方案，确认新方案会将其整份作废。请选择「替换」以新方案覆盖原方案，或选择「取消」保留原方案。",
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

        # 自然语言路径：按意图定位方案。
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
            st.pop("_pending_confirm_plan_id", None)

            le.remember(st,updated_plan)
            st["plans"].insert(0, dict(updated_plan))

            analyze_requested = bool(re.search(r"分析|营养结构|营养报告|复盘", message))
            report = None
            report_error = None
            if analyze_requested:
                _st("正在分析营养结构")
                try:
                    report = bc.nutrition_analysis(int(updated_plan["meal_plan_id"]))
                except Exception as exc:
                    report_error = str(exc)

            fallback = (
                f"已确认，方案已生效。{'已取代同期的旧方案。' if replace else ''}\n"
                + ("营养结构报告也已按最终方案生成。" if report is not None else "")
                + (f"方案已确认，但营养分析未生成：{report_error}" if report_error else "")
                + ("" if analyze_requested else "食材清单已按类别整理好，可在右侧「食材清单」查看。")
            )
            context = (
                "动作：确认/固定当前方案。\n"
                f"是否取代同期的旧方案：{'是' if replace else '否'}\n"
                f"营养分析：{'已成功生成' if report is not None else ('生成失败：' + report_error if report_error else '用户未请求')}。"
            )
            result_blocks = [blocks.meal_card_block(updated_plan)]
            if report is not None:
                result_blocks.append(blocks.report_block(report))
            if replace:
                # 「替换」是确定性动作：直接给确定文案，避免 LLM 把「替换」误读成待确认范围、再追问一次
                return {"text": fallback, "blocks": result_blocks}
            narration = _narrate(message, context, fallback, history)
            return {
                "narration": narration,
                # 【改进】发带 fixed 状态的餐卡：前端按 meal_plan_id 就地更新原卡（翻成「已生效」并禁用按钮），
                # 不在对话里追加新卡；清单只引导去右侧工具栏。
                "blocks": result_blocks,
            }
        except bc.BackendError as e:
            if getattr(e, "code", None) == 2005:  # PLAN_STATE_CONFLICT：同期已有固定方案
                # 后端消息已完整（含冲突说明），不再重复追加提示，也不重复渲染方案卡片；
                # 改用行内快捷按钮让用户二选一，点击后发「替换/取消」固定话术走意图路由。
                # 记住本次冲突的目标方案 id，供下一轮「替换/取消」在无 context 时定位（多方案场景）。
                st["_pending_confirm_plan_id"] = plan.get("meal_plan_id")
                return {
                    "text": "这段时间已有固定方案，确认新方案会将其整份作废。请选择「替换」以新方案覆盖原方案，或选择「取消」保留原方案。",
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
        # 日期字段名归一：正则路径给 period_start/period_end，LLM 分类路径按 _INTENT_SYSTEM 给
        # start_date/end_date，两路径字段名不一致会导致 custom 报告区间丢失（BUG-038）。
        period_start = intent.get("period_start") or intent.get("start_date")
        period_end = intent.get("period_end") or intent.get("end_date")

        # 膳食报告（时间段维度）：周/月/自定义，跨方案聚合，不依赖当前方案
        if scope in ("week", "month", "custom"):
            _st("正在生成膳食报告")
            try:
                if scope == "custom":
                    report = bc.period_analysis(
                        "custom",
                        period_start=period_start,
                        period_end=period_end,
                    )
                else:
                    report = bc.period_analysis(scope)
            except Exception as e:
                return {"text": f"膳食报告生成失败：{e}", "blocks": []}
            label = (
                f"{period_start}~{period_end}"
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
            content, source_footer = _rag_material(items)
        except Exception:
            content = ""
            source_footer = ""

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
            suffix = source_footer + "\n\n> 以上营养线索仅供参考、不构成医学诊断，如有不适请及时就医。"
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
            + "\n用下方方案数据解释「为什么这样搭」或回应用户对当前搭配的质疑。先一句话给结论，再按骨架展开：\n"
              "### 好在哪\n- 仅总结真正合理的餐次与做法亮点（1~3 条，每条 1 行）；若某餐已被改出双主食或缺蛋白等失衡搭配，严禁硬夸该餐；\n"
              "### 三餐怎么搭\n- 一张表格列三餐：餐次 | 能量 | 蛋白 | 核心菜；\n"
              "### 要注意\n- 点出当前方案的实际失衡风险（如双主食叠加、蛋白主菜缺位）及口径提示（1~2 条）；\n"
              "结尾一句下一步引导（只能引导系统实际支持的单步动作，如「把午餐的蒸红薯换回蛋白质主菜」或「重新生成午餐」，严禁编造加餐餐位或跨餐挪菜等不存在的功能）。\n"
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
            content, source_footer = _rag_material(items)
        except Exception:
            content = ""
            source_footer = ""

        if not content:
            return {
                "text": "知识库暂未检索到足够依据，我不会为这个问题编造来源。你可以换一个更具体的食材、营养素或人群条件再问。",
                "blocks": [],
            }

        fallback = "已根据知识库检索结果整理回答，请对照文末来源核验。"
        narration = _llm_reply(
            SYSTEM_INSTRUCTION
            + "\n只能使用下方编号资料回答，在对应结论后标注 [1] [2] 形式的引用。"
              "不得生成新的文献名、来源编号或链接。资料不足时要明说局限。"
              "注意双口径（生重/成品）与油盐话术。" + _FMT,
            f"问题：{message}\n\n编号检索资料：\n{content}",
            fallback,
            history,
        )
        return {"narration": narration, "suffix": source_footer, "blocks": []}

    # 兜底（理论上不可达：classify 的 intent 均有分支，chat/plan_*/shopping_list 已路由到 _agent_loop）
    return {"text": "这个我暂时答不好。可以让我排今天的三餐、换候选、或生成膳食报告。", "blocks": []}


def _suggestions(result: dict) -> list[str]:
    """B1 快捷追问：按本轮结果确定性生成（不调 LLM，不增加首字延迟）。

    只在 done 里下发，前端渲染成气泡下方 chip；点一下等于把该 phrase 当用户消息发回。
    """
    blocks = result.get("blocks") or []
    cards = [b for b in blocks if b.get("type") == "meal_card"]
    if cards:
        status = cards[-1].get("status")
        if status in ("draft", "candidates", "pending"):
            return ["换一道菜", "确认这份方案", "看看营养分析"]
        return ["看看营养分析", "生成膳食报告", "明天吃什么"]
    text = f"{result.get('text') or ''}{result.get('narration') or ''}"
    if "档案" in text:
        return ["现在建档", "先排今天的三餐", "我需要哪些营养素"]
    if "报告" in text or "复盘" in text:
        return ["排明天三餐", "排一周的餐", "换一道菜"]
    if any(k in text for k in ("计算", "营养素", "推荐摄入")):
        return ["按我的情况排三餐", "这个营养素在哪吃得到", "看看营养分析"]
    return ["排今天的三餐", "排一周的餐", "查营养素推荐量"]


def run(user_id: str, message: str, history: list | None = None, on_status=None,
        *, conversation_id=None, context=None) -> dict:
    """Serialize mutations per authenticated conversation; different chats stay independent."""
    with cs.locked(user_id,conversation_id) as state:
        result = _run(user_id,message,history,on_status,state=state,context=context or {})
    if "suggestions" not in result:
        result["suggestions"] = _suggestions(result)
    return result


def _week_start() -> str:
    d = date.today()
    return (d - timedelta(days=d.weekday())).isoformat()
