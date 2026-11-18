#!/usr/bin/env python
"""IMP-034 / IMP-036 增量门禁 G-D3 —— 离线部分（不需要后端隧道）。

覆盖三块新能力的可离线判定项：
  A. 生成范围自由化（plan_custom）：_is_custom_span / _resolve_gen_params / _norm_date
  B. 软偏好透传（soft_avoid）：_extract_preferences 确定性抽取 + Agent→后端 payload 透传 + 后端字段接收
  C. 反向营养映射（IMP-036）+ 空检索不伪溯源（BUG-026）：静态实现检查

需要真后端的两条（软偏好实际生效、symptom_nutrient_map 命中回落）挂在 G-D3 的 LIVE 段，
由 verify_gd3_live.py 在拿到隧道域名后执行。

用法：
    python docs/testing/automation/verify_imp034.py
退出码 0 = 全通过。
"""
from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "agent"))

import os

os.environ.setdefault("DEEPSEEK_API_KEY", "offline-dummy")

results: list[tuple[str, bool, str]] = []


def record(case: str, ok: bool, detail: str) -> None:
    results.append((case, ok, detail))


def main() -> int:
    import importlib.util

    spec = importlib.util.spec_from_file_location("_agent_mod", ROOT / "agent" / "agent.py")
    A = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(A)
    _extract_preferences = A._extract_preferences
    _is_custom_span = A._is_custom_span
    _norm_date = A._norm_date
    _resolve_gen_params = A._resolve_gen_params

    today = date.today().isoformat()
    week_end = (date.today() + timedelta(days=6)).isoformat()

    # ---------- A. 自定义范围识别 ----------
    A_CASES = [
        ("帮我配三天", True, "N 天：三天"),
        ("给我来个 5 天的食谱", True, "N 天：5 天"),
        ("配十天的", True, "N 天：中文十"),
        ("配一天", False, "1 天属单日，不走自定义"),
        ("配七天", False, "7 天属周，走 plan_week"),
        ("配7天", False, "7 天属周，走 plan_week"),
        ("11月20日到11月22日", True, "显式日期区间"),
        ("下周一三五", True, "下周语义"),
        ("这周末两天", True, "周末语义"),
        ("只排工作日的午餐", True, "工作日语义"),
        ("一周的午餐", True, "范围词 + 餐次子集"),
        ("七天早晚餐", True, "范围词 + 餐次子集"),
        ("帮我配餐", False, "无范围词"),
        ("", False, "空串不崩"),
    ]
    for msg, expect, why in A_CASES:
        got = _is_custom_span(msg)
        record("IMP034-A1", got == expect, f"_is_custom_span({msg!r})={got} 期望{expect}（{why}）")

    # ---------- A2. 参数解析 ----------
    p = _resolve_gen_params("plan_custom", {"start_date": "2026-11-20", "end_date": "2026-11-22",
                                            "meal_types": ["午餐"]})
    record("IMP034-A2", p == {"start_date": "2026-11-20", "end_date": "2026-11-22",
                              "meal_types": ["lunch"], "scope_label": "2026-11-20 ~ 2026-11-22"},
           f"区间+餐次子集 → {p}")

    p = _resolve_gen_params("plan_custom", {"start_date": "2026-11-25", "end_date": "2026-11-20",
                                            "meal_types": []})
    record("IMP034-A3", p["start_date"] == "2026-11-20" and p["end_date"] == "2026-11-25"
           and p["meal_types"] == ["breakfast", "lunch", "dinner"],
           f"倒序区间纠正 + 空餐次回退三餐 → {p}")

    p = _resolve_gen_params("plan_custom", {"start_date": "2026-11-20", "end_date": None,
                                            "meal_types": ["早餐", "晚餐", "宵夜"]})
    record("IMP034-A4", p["end_date"] == "2026-11-20" and p["meal_types"] == ["breakfast", "dinner"],
           f"缺 end 取 start + 非法餐次被过滤 → {p}")

    p = _resolve_gen_params("plan_custom", {"start_date": "编造的日期", "end_date": "", "meal_types": ["午餐"]})
    record("IMP034-A5", p["start_date"] == today and p["end_date"] == today,
           f"非法日期串回退今天（不编造日期）→ {p}")

    p = _resolve_gen_params("plan_week", {})
    record("IMP034-A6", p["start_date"] == today and p["end_date"] == week_end
           and p["meal_types"] == ["breakfast", "lunch", "dinner"], f"plan_week 仍为 7 天三餐 → {p}")

    p = _resolve_gen_params("plan_meal", {"meal_type": "晚餐"})
    record("IMP034-A7", p["end_date"] == today and p["meal_types"] == ["dinner"],
           f"plan_meal 单餐 → {p}")

    # ---------- A3. 日期归一 ----------
    norm = [("2026年11月20日", "2026-11-20"), ("2026/11/20", "2026-11-20"),
            ("2026-11-20", "2026-11-20"), ("2026-13-40", None), ("下周", None), ("", None)]
    bad = [(s, e, _norm_date(s)) for s, e in norm if _norm_date(s) != e]
    record("IMP034-A8", not bad, f"_norm_date 6 例{'全部正确' if not bad else f'异常 {bad}'}")

    # ---------- B. 软偏好确定性抽取 ----------
    pref = _extract_preferences("不要牛肉，清淡一点")
    ok = pref["exclude"] == ["牛肉"] and "油炸" in pref["soft_avoid"] and "红烧" in pref["soft_avoid"]
    record("IMP034-B1", ok, f"「不要牛肉，清淡一点」→ {pref}")

    pref = _extract_preferences("别吃花生，少放油")
    ok = pref["exclude"] == ["花生"] and "炒" in pref["soft_avoid"]
    record("IMP034-B2", ok, f"「别吃花生，少放油」→ {pref}")

    pref = _extract_preferences("我想吃清淡的鱼")
    ok = pref["exclude"] == [] and pref["soft_avoid"]
    record("IMP034-B3", ok, f"只命中软偏好、不误当硬排除 → {pref}")

    pref = _extract_preferences("")
    ok = pref["exclude"] == [] and pref["soft_avoid"] == []
    record("IMP034-B4", ok, "空串返回空结构，不崩")

    pref = _extract_preferences("不要醋")
    record("IMP034-B5", pref["exclude"] == ["醋"], f"「忌口」类短词不漏（忌(?!口) 排除干扰）→ {pref}")

    # ---------- B2. 透传链路（静态） ----------
    bc = (ROOT / "agent" / "backend_client.py").read_text(encoding="utf-8")
    record("IMP034-B6", "soft_avoid" in bc and 'payload["soft_avoid"] = soft_avoid' in bc,
           "Agent 侧 generate_meal_plan 收 soft_avoid 并写入 payload")

    mp = (ROOT / "backend" / "app" / "routers" / "mealplan.py").read_text(encoding="utf-8")
    record("IMP034-B7", re.search(r"soft_avoid:\s*list\[str\]", mp) is not None
           and "soft_avoid=req.soft_avoid" in mp,
           "后端 GenerateRequest 收 soft_avoid 并下传规则引擎")

    ag = (ROOT / "agent" / "agent.py").read_text(encoding="utf-8")
    record("IMP034-B8", 'name": "generate_plan"' in ag and "soft_avoid" in ag
           and "_agent_loop" in ag and "_TOOLS" in ag,
           "工具 schema 含 generate_plan.soft_avoid，编排循环 _agent_loop 在位")

    # ---------- C. IMP-036 反向营养 + BUG-026 不伪溯源 ----------
    ba = (ROOT / "backend" / "app" / "routers" / "agent.py").read_text(encoding="utf-8")
    record("IMP036-C1", "core.symptom_nutrient_map" in ba,
           "后端反向营养优先查 core.symptom_nutrient_map")
    record("IMP036-C2", "is_active" in ba and "aliases" in ba,
           "映射表按 is_active + aliases 子串命中")
    record("IMP036-C3", "symptom_nutrient_map" in ba and "method" in ba and "note" in ba,
           "命中/兜底在 method/note 中如实标注")

    record("BUG026-C4", "未检索到具体文献" in ag and "来自知识库" in ag,
           "Agent 按检索结果分流来源后缀，空检索明确「未检索到具体文献」")

    # ---------- 汇总 ----------
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    for case, ok, detail in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {case} {detail}")
    print(f"\n== G-D3 离线 {passed}/{total} {'PASS' if passed == total else 'FAIL'}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
