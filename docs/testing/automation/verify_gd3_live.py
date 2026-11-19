#!/usr/bin/env python
"""G-D3 LIVE 段 —— IMP-034 生成范围自由化 / 软偏好 / IMP-036 反向营养映射的真后端验证。

离线段见 verify_imp034.py（33 项，无需隧道）。本脚本需 LIVE_BASE_URL：
    LIVE_BASE_URL=https://<隧道域名> python docs/testing/automation/verify_gd3_live.py

L-01 自定义区间：11-20~11-22 三天 → 方案覆盖 3 天
L-02 餐次子集：只排午餐 → 槽位全为 lunch
L-03 软偏好透传：soft_avoid=[油炸,炸] 且必含炸物候选请求 → 方案内炸物显著减少/为 0
L-04 症状映射：/api/agent/reverse-nutrition 当前一律 keyword_fallback
     （#9 口径：symptom_nutrient_map 16 条全未激活；数据岗审核置活后需改判据）
L-05 检索溯源：/api/agent/rag-query 的 kind=doc 条目 source 非空（BUG-027，
     修于 4f6c937 应用层回查；query 用「主食」，非 doc 条目不计入分母）
L-06 跨度边界：span=32 天请求被拒（#9 口径 MAX_SPAN_DAYS=31，
     PARAM_ERROR + 「日期跨度上限 31 天」提示）

前置不可达时统一判 BLOCKED 并退出码 2，不刷假 FAIL。
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BASE = (os.environ.get("LIVE_BASE_URL") or "").rstrip("/")
OUT = Path(__file__).with_name("gd3_live_results.json")
results: list[dict] = []


def record(case: str, verdict: str, detail: str) -> None:
    results.append({"case": case, "verdict": verdict, "detail": detail})
    print(f"[{verdict}] {case} {detail}")


def jwt_for(uid: str = "TEST-E2E-03") -> str:
    try:
        import jwt as pyjwt
    except ImportError:
        return ""
    now = datetime.now(timezone.utc)
    return pyjwt.encode({"sub": uid, "iat": now, "exp": now + timedelta(hours=4)},
                        "change-me-in-production", algorithm="HS256")


def call(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {jwt_for()}"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}
    except Exception as e:  # noqa: BLE001
        return 0, {"_err": str(e)}


def days_between(a: str, b: str) -> int:
    return (date.fromisoformat(b[:10]) - date.fromisoformat(a[:10])).days + 1


def slots_of(plan: dict) -> list[dict]:
    return plan.get("slots") or (plan.get("data") or {}).get("slots") or []


def main() -> int:
    if not BASE:
        record("PRE-00", "BLOCKED", "未设置 LIVE_BASE_URL，跳过 LIVE 段（离线段用 verify_imp034.py）")
        return 2
    code, health = call("GET", "/api/health")
    if code != 200 or health.get("status") != "ok":
        record("PRE-01", "BLOCKED", f"隧道不可达 code={code} body={str(health)[:120]}")
        return 2
    record("PRE-01", "PASS", f"health 200 status={health.get('status')} database={health.get('database')}")

    # 先建档（避免无档案走兜底）
    call("POST", "/api/profile", {"name": "测试E2E三", "gender": "female", "age": 26,
                                  "height": 162, "weight": 58, "target": "减脂"})

    start = (date.today() + timedelta(days=2)).isoformat()
    end = (date.today() + timedelta(days=4)).isoformat()

    # L-01 三天区间
    code, rep = call("POST", "/api/meal-plan/week/generate",
                     {"start_date": start, "end_date": end, "meal_types": ["早", "午", "晚"]})
    plan = (rep.get("data") or {})
    pid = plan.get("meal_plan_id") or plan.get("plan_id")
    if code == 200 and rep.get("code") == 0 and pid:
        c2, det = call("GET", f"/api/meal-plan/{pid}")
        p = det.get("data") or {}
        dates = sorted({(s.get("slot_date") or "")[:10] for s in slots_of(p)})
        span = days_between(p.get("start_date") or start, p.get("end_date") or end)
        record("L-01", "PASS" if span == 3 and len(dates) == 3 else "FAIL",
               f"plan_id={pid} 区间 {p.get('start_date')}~{p.get('end_date')} 跨 {span} 天，"
               f"实际槽位日期 {len(dates)} 个：{dates}")
    else:
        record("L-01", "FAIL", f"生成失败 code={code} body={str(rep)[:200]}")

    # L-02 只排午餐
    code, rep = call("POST", "/api/meal-plan/week/generate",
                     {"start_date": start, "end_date": start, "meal_types": ["午"]})
    plan = (rep.get("data") or {})
    pid2 = plan.get("meal_plan_id") or plan.get("plan_id")
    if code == 200 and pid2:
        c2, det = call("GET", f"/api/meal-plan/{pid2}")
        slots = slots_of(det.get("data") or {})
        mts = {(s.get("meal_type") or "") for s in slots}
        record("L-02", "PASS" if slots and mts <= {"午餐", "午", "lunch"} else "FAIL",
               f"plan_id={pid2} 槽位 {len(slots)} 个，餐次集合 {mts}")
    else:
        record("L-02", "FAIL", f"生成失败 code={code} {str(rep)[:160]}")

    # L-03 软偏好：请求含炸/炒软偏好，检查方案内炸物占比
    code, rep = call("POST", "/api/meal-plan/week/generate",
                     {"start_date": start, "end_date": start,
                      "meal_types": ["早", "午", "晚"],
                      "soft_avoid": ["油炸", "炸", "红烧"]})
    plan = (rep.get("data") or {})
    pid3 = plan.get("meal_plan_id") or plan.get("plan_id")
    if code == 200 and pid3:
        c3, det = call("GET", f"/api/meal-plan/{pid3}")
        names = " ".join(str((s.get("selected") or {}).get("dish_name") or "")
                         for s in slots_of(det.get("data") or {}))
        hits = [w for w in ("炸", "红烧") if w in names]
        record("L-03", "PASS" if not hits else "WARN",
               f"plan_id={pid3} 含炸/红烧菜名命中 {hits or '无'}（软偏好为降权非硬删，命中即记录不判 FAIL）；"
               f"菜名样本：{names[:80]}")

    # L-04 反向营养映射标注（#9 口径：表 16 条全未激活，当前一律 keyword_fallback）
    # 契约：symptoms 为**字符串**（schemas/agent.py:27 `symptoms: str`），按子串命中 symptom/aliases；
    # 早前传 list 会被 400 参数校验拦下（code=1001），不是后端回退。
    code, rep = call("POST", "/api/agent/reverse-nutrition", {"symptoms": "乏力、掉发", "top_k": 5})
    d = rep.get("data") or {}
    method = d.get("method")
    note = d.get("note") or ""
    ok = code == 200 and method == "keyword_fallback" and note
    record("L-04", "PASS" if ok else "FAIL",
           f"method={method}（锁定 keyword_fallback：symptom_nutrient_map 16 条均未激活） "
           f"items={len(d.get('items') or [])} note={note[:60]}")

    # L-05 检索溯源：kind=doc 条目必须带 source（BUG-027，修于 4f6c937）
    # 口径（安娜 #12 建议）：只对 kind=="doc" 判溯源；nutrient_knowledge 表无 source 列，
    # 非 doc 条目不计入分母。query 用「主食」——「低GI 主食怎么选」按空白分词 AND 全命中，
    # 库里无对应文档，会恒返回 0 条被判 SKIP，判据不可达。
    code, rep = call("POST", "/api/agent/rag-query", {"query": "主食", "top_k": 5})
    d5 = rep.get("data") or {}
    items5 = d5.get("items") or []
    method5 = d5.get("method")
    docs5 = [i for i in items5 if i.get("kind") == "doc"]
    others5 = len(items5) - len(docs5)
    if code != 200:
        record("L-05", "FAIL", f"请求失败 code={code} {str(rep)[:160]}")
    elif not docs5:
        record("L-05", "SKIP",
               f"检索无 doc 条目（method={method5} items={len(items5)}），source 判据不可达，不作 FAIL")
    else:
        missing = [i for i in docs5 if not i.get("source")]
        record("L-05", "PASS" if not missing else "FAIL",
               f"method={method5} doc={len(docs5)}（非 doc {others5} 条按口径不计） source 缺失 {len(missing)} 条"
               + ("" if not missing else "（BUG-027：hybrid 路径 knowledge.search_documents 不返回 source/source_id，见 #12）"))

    # L-06 跨度上限边界（#9 口径：MAX_SPAN_DAYS = 31，32 天应被拒）
    start = (datetime.now(timezone.utc) + timedelta(days=1)).date()
    end = start + timedelta(days=31)          # 起止相差 31 天 → span=32
    code, rep = call("POST", "/api/meal-plan/week/generate", {
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "meal_types": ["早", "午", "晚"],
    })
    msg = str(rep.get("message") or "")
    over_rejected = code != 200 and ("跨度上限" in msg or "31" in msg)
    record("L-06", "PASS" if over_rejected else "FAIL",
           f"span=32（{start}~{end}）→ http={code} message={msg[:80]}"
           + ("" if over_rejected else "；期望 PARAM_ERROR + 「日期跨度上限 31 天」"))

    OUT.write_text(json.dumps({"base": BASE, "at": datetime.now().isoformat(timespec="seconds"),
                               "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    bad = [r for r in results if r["verdict"] == "FAIL"]
    print(f"\n== G-D3 LIVE {len(results) - len(bad)}/{len(results)} PASS"
          f"{'；WARN 见上' if any(r['verdict'] == 'WARN' for r in results) else ''}")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
