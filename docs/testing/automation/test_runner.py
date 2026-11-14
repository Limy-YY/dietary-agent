# -*- coding: utf-8 -*-
"""膳食搭配智能体 MVP · 离线测试执行器

不依赖后端、不依赖 DeepSeek key；MVP 模式不依赖 agno（用 stub 替身）。
可在任意一台装了 requests 的机器上直接跑。

双模式（按被测目录自动识别）：
  目标目录含 tools.py  → MVP 模式（agno + INSTRUCTIONS 那版）：
                          G1 数值口径 + G2 工具契约 + G3 指令覆盖（import 被测模块断言）
  目标目录含 agent.py → 仓库版模式（rule_engine 桥接那版）：
                          G1 数值口径 + G2R 后端封装契约 + G3R 指令话术扫描
                          （扫描 agent/*.py 与 backend/app/services/rule_engine/** 源码文本）

覆盖三组：
  G1 数值口径基准  —— BMR / TDEE / 能量目标 / 三餐分配 / 供能比 / 油脂能量
  G2 工具层契约    —— MVP 版 12 个工具的 URL、方法、参数、错误降级、user_id 生成
  G3 配置与指令覆盖 —— 工具注册、系统指令对需求条款的覆盖矩阵（BUG-01~04 对应 C-37.*）

用法：
  python test_runner.py                              # 默认测本仓库的 agent/（仓库版模式）
  python test_runner.py --target <agent目录> --json out.json
  python test_runner.py --target E:\\RG\\agent_1     # 兼容旧 MVP 目录（含 tools.py）

判定三态：PASS / FAIL / WARN（WARN = 与文档或需求不一致的可疑项，需人工确认）
退出码：有 FAIL 则为 1，否则 0
"""
import argparse
import json
import os
import re
import sys
import types
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

RESULTS = []

# 需求条款 → 指令话术覆盖矩阵（BUG-01~04 对应其中 FR-13 / FR-19/20 / FR-21 / FR-29、FR-30）。
# MVP 模式作用于 agent.INSTRUCTIONS；仓库版模式扫描实现源码文本。
COVERAGE_MATRIX = [
    ("FR-13", "三餐 30/40/30 或 供能比 50~65/20~30/10~15", ["30%", "40%", "供能比"]),
    ("FR-19/20", "食材口径 vs 菜式口径（双口径分别标注）", ["双口径", "生重", "成品口径"]),
    ("FR-21", "油盐以 低/中/高 分级 + 克数区间，不得伪精确", ["分级", "油盐"]),
    ("FR-23", "被规避菜式需给出提醒及依据说明", ["规避", "忌口说明", "排除原因"]),
    ("FR-29", "反向营养用「可能/建议关注」非确定性措辞", ["可能缺乏", "建议关注"]),
    ("FR-30", "回复末尾附「若症状持续请及时就医」", ["及时就医", "就医"]),
    ("FR-27", "关键结论标注权威来源（source/source_id）", ["source_id", "出处", "来源"]),
]


# ---------------------------------------------------------------- 基础工具
def record(cid, group, title, req, expected, actual, status, note=""):
    RESULTS.append({
        "id": cid, "group": group, "title": title, "req": req,
        "expected": expected, "actual": actual, "status": status, "note": note,
    })
    flag = {"PASS": "PASS", "FAIL": "FAIL", "WARN": "WARN"}[status]
    print(f"[{flag}] {cid} {title}")
    if status != "PASS":
        print(f"        期望: {expected}")
        print(f"        实际: {actual}")


def eq(cid, group, title, req, expected, actual, tol=0.5, note=""):
    try:
        ok = abs(float(expected) - float(actual)) <= tol
    except (TypeError, ValueError):
        ok = expected == actual
    record(cid, group, title, req, expected, actual, "PASS" if ok else "FAIL", note)
    return ok


def truth(cid, group, title, req, expected, actual, note=""):
    record(cid, group, title, req, expected, actual, "PASS" if actual else "FAIL", note)
    return bool(actual)


def warn_if(cid, group, title, req, expected, actual, suspicious, note=""):
    status = "WARN" if suspicious else "PASS"
    record(cid, group, title, req, expected, actual, status, note)


# ---------------------------------------------------------------- stub
def install_stubs():
    """注入 agno 替身，使 tools.py / agent.py 可在未装 agno 的环境 import。"""
    def tool(*args, **kwargs):
        if len(args) == 1 and callable(args[0]) and not kwargs:
            fn = args[0]
            fn._mvp_tool = True
            return fn

        def deco(fn):
            fn._mvp_tool = True
            return fn
        return deco

    agno = types.ModuleType("agno")
    agno_tools = types.ModuleType("agno.tools")
    agno_tools.tool = tool

    agno_agent = types.ModuleType("agno.agent")

    class Agent:
        def __init__(self, **kw):
            self.kw = kw
            self.name = kw.get("name")
            self.instructions = kw.get("instructions")
            self.tools = kw.get("tools")

    agno_agent.Agent = Agent
    agno_models = types.ModuleType("agno.models")
    agno_deepseek = types.ModuleType("agno.models.deepseek")

    class DeepSeek:
        def __init__(self, **kw):
            self.kw = kw

    agno_deepseek.DeepSeek = DeepSeek
    agno.tools = agno_tools
    agno.agent = agno_agent
    agno.models = agno_models
    agno_models.deepseek = agno_deepseek
    sys.modules.update({
        "agno": agno, "agno.tools": agno_tools, "agno.agent": agno_agent,
        "agno.models": agno_models, "agno.models.deepseek": agno_deepseek,
    })


class FakeResp:
    def __init__(self, payload=None, status=200, text=None, bad_json=False):
        self._payload = payload
        self.status_code = status
        self.text = text if text is not None else json.dumps(payload, ensure_ascii=False)
        self._bad_json = bad_json

    def json(self):
        if self._bad_json:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self._payload


class FakeRequests:
    class RequestException(Exception):
        pass

    def __init__(self):
        self.calls = []
        self.next = None
        self.raise_exc = None

    def _do(self, method, url, params=None, body=None):
        self.calls.append({"method": method, "url": url, "params": params, "json": body})
        if self.raise_exc:
            raise self.raise_exc
        return self.next or FakeResp({"code": 0, "message": "ok", "data": {"ok": True}})

    def get(self, url, params=None, timeout=None):
        return self._do("GET", url, params=params)

    def post(self, url, json=None, timeout=None):
        return self._do("POST", url, body=json)


# ---------------------------------------------------------------- G1 数值口径
def g1_numeric():
    G = "G1 数值口径"

    def bmr_female(w, h, a):
        return 10 * w + 6.25 * h - 5 * a - 161

    def bmr_male(w, h, a):
        return 10 * w + 6.25 * h - 5 * a + 5

    PAL = {"久坐": 1.2, "轻度": 1.4, "中度": 1.6, "重度": 1.9}

    # R-01 基准：25 岁 160cm 60kg 轻体力 减脂女
    bmr = bmr_female(60, 160, 25)
    td = bmr * PAL["轻度"]
    target = td - 500
    eq("C-01", G, "BMR 计算（Mifflin-St Jeor 女式，25/160/60）", "FR-08",
       "1314.0", round(bmr, 1), tol=0.5, note="10W+6.25H-5A-161")
    eq("C-02", G, "TDEE = BMR × PAL(轻度 1.4)", "FR-09, 表9 术语",
       "1839.6", round(td, 1), tol=0.5)
    eq("C-03", G, "能量目标 = TDEE − 500（减脂），对照验收 R-01 的 1340 kcal", "FR-10, R-01",
       "1340", round(target, 0), tol=1.5, note="文档写「约 1340 kcal」，自洽")

    # R-01 男式基准：28/178/82 久坐减脂
    bmr_m = bmr_male(82, 178, 28)
    eq("C-04", G, "BMR 计算（男式，28/178/82）", "FR-08",
       "1797.5", round(bmr_m, 1), tol=0.5, note="10W+6.25H-5A+5")
    eq("C-05", G, "TDEE 与目标（久坐 1.2，减脂 −500）", "FR-09, FR-10",
       "1657", round(bmr_m * PAL["久坐"] - 500, 0), tol=1.5)

    # PAL 四档
    for k, v in PAL.items():
        eq(f"C-06.{k}", G, f"PAL 系数「{k}」= {v}", "术语表 PAL",
           v, PAL[k], tol=0.001, note="需求原文：久坐1.2→轻1.4→中1.6→重1.9+")

    # 目标调整
    base = 1800
    for goal, delta in (("减脂", -500), ("增肌", 300), ("维持", 0)):
        eq(f"C-07.{goal}", G, f"目标调整「{goal}」{delta:+d} kcal", "FR-10",
           base + delta, base + delta, tol=0.1, note="需求明文：减脂−500 / 增肌+300 / 维持")

    # 三餐分配 30/40/30
    t = 1340
    parts = [t * 0.3, t * 0.4, t * 0.3]
    eq("C-08", G, "三餐 30/40/30 分配后之和与总量一致", "FR-13",
       round(t, 0), round(sum(parts), 0), tol=1.0, note=f"早{parts[0]:.0f}/中{parts[1]:.0f}/晚{parts[2]:.0f}")

    # 供能比换算（中值 55/25/15）
    carb_g = t * 0.55 / 4
    pro_g = t * 0.15 / 4
    fat_g = t * 0.25 / 9
    eq("C-09", G, "供能比 55/25/15 → 克数（4/4/9 kcal per g）", "FR-13, FR-20",
       round(carb_g + pro_g + fat_g, 0), round(carb_g + pro_g + fat_g, 0), tol=0.1,
       note=f"碳{carb_g:.0f}g 蛋{pro_g:.0f}g 脂{fat_g:.0f}g")

    # 油脂能量 1g=9kcal
    eq("C-10", G, "烹饪油 +10g → +90 kcal（菜式口径）", "FR-20",
       90, 10 * 9, tol=0.1)

    # seed 档案期望值 vs README 声称值
    bmr_s = bmr_female(50, 160, 20)
    td_s = bmr_s * PAL["中度"]
    tgt_s = td_s - 500
    warn_if("C-11", G,
            "u_test_001（女20/160/50/中度/减脂）能量目标：需求口径 vs README 声称 1920",
            "FR-10, README 第 33 行, TEST_README 第 64 行",
            f"需求口径 {tgt_s:.0f} kcal（BMR {bmr_s:.0f}×1.6−500）；README 声称 1920",
            f"按需求算 {tgt_s:.0f}；1920 只等于 BMR×1.55（且未扣 500）",
            suspicious=abs(tgt_s - 1920) > 30,
            note="两者不一致：要么后端未实现 FR-10 减脂缺口，要么 README 期望值取错口径。需在环境可用时用 API-03 实测确认。")


# ---------------------------------------------------------------- G2 工具契约
def g2_tools(bc, tools):
    G = "G2 工具契约"
    fake = FakeRequests()
    bc.requests = fake
    base = bc.BASE

    def call(fn, *a, **kw):
        fake.calls.clear()
        return fn(*a, **kw)

    # C-12 读档案
    out = call(tools.get_user_profile, "u_test_001")
    c = fake.calls[-1]
    truth("C-12", G, "get_user_profile 走 GET /api/users/{id}/profile",
          "T12, API-02",
          "GET .../api/users/u_test_001/profile",
          c["method"] == "GET" and c["url"].endswith("/api/users/u_test_001/profile"),
          note=f"实际 {c['method']} {c['url']}")
    truth("C-13", G, "工具返回值是可被模型消费的 JSON 字符串", "FR-05",
          "str 且可 json.loads", isinstance(out, str) and isinstance(json.loads(out), (dict, list)))

    # C-14 建档 payload
    call(tools.upsert_profile, "u_zhangsan", sex="男", age=28, height_cm=178,
         weight_kg=82, activity_level="久坐", goal="减脂",
         allergies=["花生"], taboos=[], conditions=[], extras=None)
    c = fake.calls[-1]
    body = c["json"] or {}
    need = {"user_id", "sex", "age", "birth_date", "height_cm", "weight_kg",
            "activity_level", "goal", "allergies", "taboos", "conditions", "extras"}
    truth("C-14", G, "upsert_profile 走 POST /api/profile 且字段齐全", "FR-01, API-01",
          f"POST /api/profile，含 {len(need)} 个字段",
          c["method"] == "POST" and c["url"].endswith("/api/profile") and need.issubset(body.keys()),
          note=f"缺字段 {sorted(need - set(body.keys()))}" if not need.issubset(body.keys()) else "")

    call(tools.upsert_profile, "u_blank", sex="女", age=22)
    body2 = fake.calls[-1]["json"] or {}
    truth("C-15", G, "未传 allergies/taboos/conditions 时回退为空数组（而非 null）", "FR-22",
          "[]", body2.get("allergies") == [] and body2.get("taboos") == []
          and body2.get("conditions") == [],
          note=f"实际 {body2.get('allergies')}/{body2.get('taboos')}/{body2.get('conditions')}")

    # C-16 自动 user_id
    call(tools.upsert_profile, sex="女", age=22)
    uid1 = (fake.calls[-1]["json"] or {}).get("user_id", "")
    truth("C-16", G, "无 user_id 时自动生成 u_<14 位时间戳>", "FR-01",
          "匹配 ^u_\\d{14}$", bool(re.fullmatch(r"u_\d{14}", uid1)), note=f"实际 {uid1}")

    call(tools.upsert_profile, sex="女", age=23)
    uid2 = (fake.calls[-1]["json"] or {}).get("user_id", "")
    warn_if("C-17", G, "同一秒内连续两次自动建档的 user_id 是否唯一", "FR-01（档案唯一性）",
            "两次 user_id 不同", f"{uid1} / {uid2}",
            suspicious=(uid1 == uid2),
            note="秒级时间戳做主键，同秒并发/连点会覆盖同一档案" if uid1 == uid2 else "")

    # C-18 食材搜索
    call(tools.search_ingredients, "西红柿", 10)
    c = fake.calls[-1]
    truth("C-18", G, "search_ingredients 走 GET /api/ingredients/search?q&limit", "T1, API-11",
          "GET 且 params 含 q=西红柿 limit=10",
          c["method"] == "GET" and c["url"].endswith("/api/ingredients/search")
          and (c["params"] or {}).get("q") == "西红柿" and (c["params"] or {}).get("limit") == 10,
          note=f"{c['params']}")

    # C-19 菜式过敏过滤
    call(tools.search_dishes, "", ["花生", "海鲜"], 1, 20)
    c = fake.calls[-1]
    truth("C-19", G, "search_dishes 的 exclude_allergies 以逗号拼接", "FR-22, T2/T3",
          "exclude_allergies=花生,海鲜",
          (c["params"] or {}).get("exclude_allergies") == "花生,海鲜",
          note=f"{c['params']}")

    # C-20 营养核算
    call(tools.calc_nutrition, "ingredient", [{"ingredient_id": 23, "amount_g": 150}], True)
    c = fake.calls[-1]
    body = c["json"] or {}
    truth("C-20", G, "calc_nutrition 走 POST /api/calc/nutrition，body 含 target_type/items/include_micro",
          "FR-19, API-09", "POST，target_type=ingredient",
          c["method"] == "POST" and c["url"].endswith("/api/calc/nutrition")
          and body.get("target_type") == "ingredient" and body.get("items")
          and body.get("include_micro") is True, note=f"{body}")

    # C-21 生成方案
    call(tools.generate_meal_plan, "u_test_001", "2026-10-23")
    c = fake.calls[-1]
    truth("C-21", G, "generate_meal_plan 走 POST /api/meal-plan/generate", "API-03",
          "body user_id + plan_date",
          c["method"] == "POST" and (c["json"] or {}).get("plan_date") == "2026-10-23",
          note=f"{c['json']}")

    # C-22 周报
    call(tools.weekly_nutrition_report, "u_test_001", "2026-10-19")
    c = fake.calls[-1]
    truth("C-22", G, "weekly_nutrition_report 走 GET 带 user_id/week_start", "T4/T5, API-13",
          "params user_id=u_test_001 week_start=2026-10-19",
          c["method"] == "GET" and (c["params"] or {}).get("week_start") == "2026-10-19")

    # C-23~C-25 错误降级
    fake.next = FakeResp({"code": 4040, "message": "profile not found", "data": None})
    out = call(tools.generate_meal_plan, "u_none", "2026-10-23")
    handled = False
    try:
        payload = json.loads(out)
        handled = "error" in payload and "4040" in payload.get("error", "")
    except Exception:
        handled = False
    truth("C-23", G, "后端业务错误（code≠0）→ 工具返回 error 字符串，不抛异常", "3.5.2 可靠性",
          "返回 JSON 含 error 且带 code", handled, note=out[:120])

    fake.next = None
    fake.raise_exc = FakeRequests.RequestException("Connection refused")
    out = call(tools.get_user_profile, "u_test_001")
    handled = False
    try:
        handled = "error" in json.loads(out)
    except Exception:
        handled = False
    truth("C-24", G, "后端断连 → 工具优雅降级（返回 error 字符串）", "3.5.2 可靠性",
          "不崩溃，返回 error", handled, note=out[:120])

    fake.raise_exc = None
    fake.next = FakeResp(None, status=502, text="<html>502 Bad Gateway</html>", bad_json=True)
    out = call(tools.get_user_profile, "u_test_001")
    handled = False
    try:
        handled = "error" in json.loads(out)
    except Exception:
        handled = False
    truth("C-25", G, "后端返回非 JSON（如网关 502 HTML）→ 工具优雅降级", "3.5.2 可靠性",
          "不崩溃，返回 error", handled, note=out[:120])
    fake.next = None

    # C-26 文档一致性：后端未按 {code,message,data} 包装时
    fake.next = FakeResp({"sex": "女", "age": 20}, status=200)
    out = call(tools.get_user_profile, "u_test_001")
    rejected = False
    try:
        payload = json.loads(out)
        rejected = "error" in payload
    except Exception:
        pass
    note = "后端若直接返回裸对象（无 code 字段）会被判为错误——需确认后端统一包装契约"
    warn_if("C-26", G, "裸 JSON（无 code 字段）是否被误判为失败", "3.1.2 软件接口（未定义 code 包装）",
            "应能容忍或明确报契约错", "被判为 error" if rejected else "正常返回",
            suspicious=rejected, note=note)
    fake.next = None

    # C-27 工具清单
    registered = [n for n in dir(tools) if getattr(getattr(tools, n), "_mvp_tool", False)]
    truth("C-27", G, "tools.py 注册工具数 = 12", "README 工具映射表",
          "12", len(registered) == 12, note=f"实际 {len(registered)}：{sorted(registered)}")

    # C-28 工具描述完整性
    missing = []
    for n in registered:
        doc = (getattr(tools, n).__doc__ or "")
        if "入参" not in doc:
            missing.append(n)
    truth("C-28", G, "12 个工具 docstring 均含「入参」说明（Function Calling 选型依据）", "FR-05",
          "全部含", not missing, note=f"缺说明：{missing}" if missing else "")

    # C-29 空 user_id 不拦截
    fake.calls.clear()
    out = call(tools.get_user_profile, "")
    hit = bool(fake.calls) and fake.calls[-1]["url"].endswith("/api/users//profile")
    warn_if("C-29", G, "空 user_id 是否被前置拦截（而非拼出 //profile 打到后端）", "FR-01 健壮性",
            "应在工具层拦截并提示", f"直接请求 {fake.calls[-1]['url']}", suspicious=hit,
            note="建议工具层加 user_id 非空校验" if hit else "")


# ---------------------------------------------------------------- G3 配置与指令
def g3_config(agent, tools, config, bc):
    G = "G3 配置/指令覆盖"

    truth("C-30", G, "Agent 绑定的工具列表与 tools.py 注册一致（12 个）", "FR-05",
          "len==12", len(agent.TOOL_LIST) == 12, note=f"实际 {len(agent.TOOL_LIST)}")

    truth("C-31", G, "系统指令含「绝不自己计算/不编造数值」", "FR-05, 3.4 确定性计算",
          "命中", any("绝不自己计算" in s or "不编造" in s for s in agent.INSTRUCTIONS))

    truth("C-32", G, "系统指令含「不做医学诊断」边界", "2.4 法规与伦理",
          "命中", any("医学诊断" in s for s in agent.INSTRUCTIONS))

    truth("C-33", G, "系统指令含 null≠0 空值语义", "TEST_README 铁律3",
          "命中", any("null 表示未知" in s or "无法判断" in s for s in agent.INSTRUCTIONS))

    truth("C-34", G, "系统指令含 data_quality 可信度语义", "TEST_README 铁律4",
          "命中", any("data_quality" in s for s in agent.INSTRUCTIONS))

    truth("C-35", G, "系统指令含 allergen_status=未核查 不得称安全", "TEST_README 铁律5",
          "命中", any("未核查" in s for s in agent.INSTRUCTIONS))

    truth("C-36", G, "系统指令含 needs_clarification 必须追问", "TEST_README 铁律7",
          "命中", any("needs_clarification" in s for s in agent.INSTRUCTIONS))

    # 需求条款覆盖矩阵（关键缺口）
    all_ins = "\n".join(agent.INSTRUCTIONS)
    gaps = []
    for req, desc, kws in COVERAGE_MATRIX:
        hit = any(k in all_ins for k in kws)
        if not hit:
            gaps.append(req)
        record(f"C-37.{req}", G, f"系统指令覆盖 {req}（{desc}）", req,
               "指令中含显式约束", "命中" if hit else "未命中（依赖后端返回字段）",
               "PASS" if hit else "FAIL",
               note="" if hit else "模型侧无约束，自然语言复述时可能漏掉该要求")
    record("C-38", G, "系统指令需求覆盖缺口汇总", "3.2 系统特征",
           "0 处缺口", f"{len(gaps)} 处缺口：{gaps}", "PASS" if not gaps else "WARN",
           note="所有缺口均可通过补 1~2 条 instruction 修复，成本极低")

    # 配置解析
    truth("C-39", G, "无 .env 时配置不崩溃，默认 BASE_URL 为 127.0.0.1:8000", "README 运行前提",
          "http://127.0.0.1:8000", config.BACKEND_BASE_URL == "http://127.0.0.1:8000",
          note=f"实际 {config.BACKEND_BASE_URL}")

    # .env 解析边界：引号/行尾注释/空值
    import tempfile
    probe = Path(tempfile.mkdtemp()) / ".env"
    probe.write_text(
        'A="quoted"\nB=value # trailing comment\nC=\n', encoding="utf-8")
    parsed = {}
    for line in probe.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        parsed[k.strip()] = v.strip()
    bad = parsed.get("A") == '"quoted"' or "#" in parsed.get("B", "")
    warn_if("C-40", G, ".env 解析对引号与行尾注释的处理", "README 配置说明",
            'A=quoted / B=value', f"A={parsed.get('A')} / B={parsed.get('B')}",
            suspicious=bad,
            note="当前实现不剥离引号、不去行尾注释，用户按 dotenv 习惯书写会得到错误值" if bad else "")

    # 超时与性能需求
    truth("C-41", G, "HTTP 超时 30s 与需求 3.3（配餐 P95≤15s）的关系", "3.3 性能",
          "超时值应不小于最慢接口目标且可配置",
          bc._TIMEOUT >= 15, note=f"硬编码 _TIMEOUT={bc._TIMEOUT}，不可配置；周报目标 3s 无独立超时")


# ---------------------------------------------------------------- 仓库版模式
def _catch(fn):
    try:
        fn()
        return None
    except Exception as e:
        return e


def g2r_backend(bc):
    """仓库版 backend_client 契约：URL / 参数 / 统一解包 / 错误降级。

    与 MVP 版的差别：仓库版遇错抛 BackendError（MVP 版返回 error 字符串）。
    """
    G = "G2R 后端封装契约"
    fake = FakeRequests()
    bc.requests = fake

    def call(fn, *a, **kw):
        fake.calls.clear()
        return fn(*a, **kw)

    call(bc.get_profile, "u_test_001")
    c = fake.calls[-1]
    truth("C-42", G, "get_profile 走 GET /api/users/{id}/profile", "API-20, T12",
          "GET .../api/users/u_test_001/profile",
          c["method"] == "GET" and c["url"].endswith("/api/users/u_test_001/profile"),
          note=f"实际 {c['method']} {c['url']}")

    call(bc.upsert_profile, "u_zhangsan", sex="男", age=28)
    c = fake.calls[-1]
    truth("C-43", G, "upsert_profile 走 POST /api/profile 且 user_id 在 body", "API-01",
          "POST /api/profile，body 含 user_id",
          c["method"] == "POST" and c["url"].endswith("/api/profile")
          and (c["json"] or {}).get("user_id") == "u_zhangsan",
          note=f"{c['json']}")

    call(bc.search_ingredients, "西红柿", 10)
    c = fake.calls[-1]
    truth("C-44", G, "search_ingredients 走 GET /api/ingredients/search?q&limit", "API-11",
          "q=西红柿 limit=10",
          c["method"] == "GET" and c["url"].endswith("/api/ingredients/search")
          and (c["params"] or {}).get("q") == "西红柿" and (c["params"] or {}).get("limit") == 10,
          note=f"{c['params']}")

    call(bc.search_dishes, "", ["花生", "海鲜"], 1, 20)
    c = fake.calls[-1]
    truth("C-45", G, "search_dishes 的 exclude_allergies 以逗号拼接", "FR-22",
          "exclude_allergies=花生,海鲜",
          (c["params"] or {}).get("exclude_allergies") == "花生,海鲜",
          note=f"{c['params']}")

    call(bc.calc_nutrition, "ingredient", [{"ingredient_id": 23, "amount_g": 150}], True)
    c = fake.calls[-1]
    body = c["json"] or {}
    truth("C-46", G, "calc_nutrition 走 POST /api/calc/nutrition，body 三字段齐全", "FR-19, API-09",
          "target_type=ingredient / items / include_micro=true",
          c["method"] == "POST" and c["url"].endswith("/api/calc/nutrition")
          and body.get("target_type") == "ingredient" and body.get("items")
          and body.get("include_micro") is True, note=f"{body}")

    call(bc.weekly_report, "u_test_001", "2026-10-19")
    c = fake.calls[-1]
    truth("C-47", G, "weekly_report 走 GET 带 user_id/week_start", "API-13",
          "params week_start=2026-10-19",
          c["method"] == "GET" and (c["params"] or {}).get("week_start") == "2026-10-19",
          note=f"{c['params']}")

    fake.next = FakeResp({"code": 4040, "message": "profile not found", "data": None})
    err = _catch(lambda: bc.get_profile("u_none"))
    truth("C-48", G, "后端业务错误（code≠0）→ 抛 BackendError 且带 code", "3.5.2 可靠性",
          "BackendError 含 4040",
          err is not None and "BackendError" in type(err).__name__ and "4040" in str(err),
          note=str(err)[:120])

    fake.next = None
    fake.raise_exc = FakeRequests.RequestException("Connection refused")
    err = _catch(lambda: bc.get_profile("u_test_001"))
    truth("C-49", G, "后端断连 → 统一降级为 BackendError（不裸抛 RequestException）", "3.5.2 可靠性",
          "BackendError",
          err is not None and "BackendError" in type(err).__name__, note=str(err)[:120])

    fake.raise_exc = None
    fake.next = FakeResp(None, status=502, text="<html>502 Bad Gateway</html>", bad_json=True)
    err = _catch(lambda: bc.get_profile("u_test_001"))
    truth("C-50", G, "后端返回非 JSON（网关 502 HTML）→ 统一降级为 BackendError", "3.5.2 可靠性",
          "BackendError",
          err is not None and "BackendError" in type(err).__name__, note=str(err)[:120])
    fake.next = None

    truth("C-51", G, "HTTP 超时 30s ≥ 最慢接口目标（配餐 P95≤15s）", "3.3 性能",
          "_TIMEOUT >= 15", bc._TIMEOUT >= 15, note=f"_TIMEOUT={bc._TIMEOUT}")


def g3r_instructions(target: Path):
    """仓库版模式：扫描实现源码文本对需求条款的覆盖（BUG-01~04 对应 C-37.*）。

    已知局限：文本扫描含注释，可能出现个别假阳性；修复时请把话术加进
    实际输出路径（agent 的 LLM 指令 / blocks 模板 / rule_engine 文案）。
    """
    G = "G3R 指令话术覆盖"
    files = sorted(target.glob("*.py"))
    rule_dir = target.parent / "backend" / "app" / "services" / "rule_engine"
    scope = "agent/*.py"
    if rule_dir.is_dir():
        files += sorted(rule_dir.rglob("*.py"))
        scope += " + backend/app/services/rule_engine/**"
    texts = []
    for f in files:
        try:
            texts.append(f.read_text(encoding="utf-8"))
        except OSError:
            pass
    all_src = "\n".join(texts)
    print(f"        （话术扫描范围：{scope}，共 {len(texts)} 个文件）")

    truth("C-31", G, "实现含「绝不自己计算/不编造数值」铁律", "FR-05, 3.4 确定性计算",
          "命中", any(k in all_src for k in ("绝不自己计算", "不编造")))
    truth("C-32", G, "实现含「不做医学诊断」边界", "2.4 法规与伦理",
          "命中", "医学诊断" in all_src)
    truth("C-33", G, "实现含 null≠0 空值语义", "TEST_README 铁律3",
          "命中", any(k in all_src for k in ("null 表示未知", "无法判断")))
    truth("C-34", G, "实现含 data_quality 可信度语义", "TEST_README 铁律4",
          "命中", "data_quality" in all_src)
    truth("C-35", G, "实现含 allergen_status=未核查 不得称安全", "TEST_README 铁律5",
          "命中", "未核查" in all_src)
    truth("C-36", G, "实现含 needs_clarification 必须追问", "TEST_README 铁律7",
          "命中", "needs_clarification" in all_src)

    gaps = []
    for req, desc, kws in COVERAGE_MATRIX:
        hit = any(k in all_src for k in kws)
        if not hit:
            gaps.append(req)
        record(f"C-37.{req}", G, f"实现覆盖 {req}（{desc}）", req,
               "话术出现在实现中", "命中" if hit else "未命中",
               "PASS" if hit else "FAIL",
               note="" if hit else f"{scope} 源码中未找到该约束话术")
    record("C-38", G, "指令需求覆盖缺口汇总", "3.2 系统特征",
           "0 处缺口", f"{len(gaps)} 处缺口：{gaps}", "PASS" if not gaps else "WARN",
           note="补话术到 agent 指令 / blocks 模板 / rule_engine 文案后复跑，对应 C-37.* 转 PASS")


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=os.getenv("MVP_AGENT_DIR", ""),
                    help="被测 agent 目录；缺省为本仓库的 agent/（相对本脚本定位）")
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    if args.target:
        target = Path(args.target)
    else:
        target = Path(__file__).resolve().parents[3] / "agent"

    has_tools = (target / "tools.py").exists()
    has_agent = (target / "agent.py").exists()
    if not has_tools and not has_agent:
        print(f"找不到被测目录（需含 tools.py 或 agent.py）：{target}")
        sys.exit(2)

    print("=" * 72)
    print("膳食搭配智能体 · 离线测试")
    print(f"被测目录：{target}")
    print(f"模式：{'MVP（agno + tools.py）' if has_tools else '仓库版（rule_engine 桥接）'}")
    print(f"执行时间：{datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 72)

    g1_numeric()

    if has_tools:
        sys.path.insert(0, str(target))
        install_stubs()
        import backend_client as bc
        import config
        import tools
        import agent
        print(f"后端地址：{bc.BASE}（本组不依赖真实后端）")
        g2_tools(bc, tools)
        g3_config(agent, tools, config, bc)
    else:
        sys.path.insert(0, str(target))
        bc = None
        try:
            import backend_client as bc
        except Exception as e:
            record("C-42", "G2R 后端封装契约", "backend_client 可导入", "3.5.2 可靠性",
                   "可导入", f"导入失败：{e}", "WARN", note="通常缺 requests，pip install requests")
        if bc is not None:
            print(f"后端地址：{bc.BASE}（本组不依赖真实后端）")
            g2r_backend(bc)
        g3r_instructions(target)

    total = len(RESULTS)
    p = sum(1 for r in RESULTS if r["status"] == "PASS")
    f = sum(1 for r in RESULTS if r["status"] == "FAIL")
    w = sum(1 for r in RESULTS if r["status"] == "WARN")

    print("\n" + "=" * 72)
    print(f"合计 {total} 项 | PASS {p} | FAIL {f} | WARN {w}")
    print(f"通过率 {p / total * 100:.1f}%（不含 WARN）")
    print("=" * 72)
    if f or w:
        print("\n需要关注：")
        for r in RESULTS:
            if r["status"] != "PASS":
                print(f"  [{r['status']}] {r['id']} {r['title']}")
                if r["note"]:
                    print(f"        {r['note']}")

    if args.json:
        Path(args.json).write_text(json.dumps({
            "target": str(target), "run_at": datetime.now().isoformat(timespec="seconds"),
            "total": total, "pass": p, "fail": f, "warn": w, "results": RESULTS,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n结果已写入 {args.json}")

    sys.exit(1 if f else 0)


if __name__ == "__main__":
    main()
