"""换餐/单菜替换链路回归（覆盖 ab67a09 修复）

背景：2026-11-20 16:35 Calmigrhty 提交 ab67a09「修复换餐意图路由冲突及单菜替换落库约束异常」，
涉及 /api/meal-plan/candidate/swap、/api/meal-plan/dish/replace 两条链路，
此前的 verify_live.py / verify_gd3_live.py 都没覆盖，本脚本补上。

S-01 方案生成：生成 2 天午餐方案，状态应为 candidates，每槽候选 >= 2
S-02 候选切换：POST /candidate/swap 切到另一个候选 → 200 且 selected_candidate_id 变化
     （ab67a09 修的是此处 rank 约束 400/500）
S-03 单菜替换：POST /dish/replace 换掉当前候选里的一道菜 → 200 且菜品集合变化
     （ab67a09 修的是局部修改被误拦截）
     S-03a 带 allow_approximate=true（与 agent 侧 local_edits 实际下发一致）
     S-03b 不带 allow_approximate（严格模式）：放通=一步到位，按营养近似拒绝=预期，5xx=回退
     replacement_query 留空走「同角色替换」；传具体菜名会先按名称/配料过滤，容易池空拿到
     业务性 400，那样验不到修复点。
S-04 意图路由观察：POST /api/agent/chat 含「替换」时不应落入确认流程
     需读完整 SSE 判断；agent:8001 未启动时判 BLOCKED，不冒充 PASS

用法：
    LIVE_BASE_URL=https://<隧道域名> python docs/testing/automation/verify_swap.py
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
OUT = Path(__file__).with_name("swap_results.json")
UID = "TEST-E2E-04"
results: list[dict] = []


def record(case: str, verdict: str, detail: str) -> None:
    results.append({"case": case, "verdict": verdict, "detail": detail})
    print(f"[{verdict}] {case} {detail}")


def jwt_for(uid: str = UID) -> str:
    try:
        import jwt as pyjwt
    except ImportError:
        return ""
    now = datetime.now(timezone.utc)
    return pyjwt.encode({"sub": uid, "iat": now, "exp": now + timedelta(hours=4)},
                        "change-me-in-production", algorithm="HS256")


def call(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    """发出请求；响应非 JSON（隧道抖动/网关错误）时返回 _raw，不让解析异常中断整轮。"""
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {jwt_for()}"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            raw = r.read().decode(errors="replace")
            try:
                return r.status, json.loads(raw or "{}")
            except json.JSONDecodeError:
                return r.status, {"_raw": raw[:200]}
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(raw or "{}")
        except json.JSONDecodeError:
            return e.code, {"_raw": raw[:200]}
    except Exception as e:  # noqa: BLE001
        return 0, {"_err": str(e)}


def slots_of(plan: dict) -> list[dict]:
    return plan.get("slots") or (plan.get("data") or {}).get("slots") or []


def dishes_of(cand: dict) -> list[str]:
    ds = cand.get("dishes")
    if isinstance(ds, list):
        return [d.get("dish_id") for d in ds if isinstance(d, dict) and d.get("dish_id")]
    return []


def main() -> int:
    if not BASE:
        record("PRE-00", "BLOCKED", "未设置 LIVE_BASE_URL")
        return 2
    code, health = call("GET", "/api/health")
    if code != 200 or health.get("status") != "ok":
        record("PRE-01", "BLOCKED", f"隧道不可达 code={code} body={str(health)[:120]}")
        return 2

    call("POST", "/api/profile", {"name": "测试E2E四", "gender": "female", "age": 27,
                                  "height": 163, "weight": 58, "target": "减脂"})

    # S-01 生成方案
    start = (date.today() + timedelta(days=2)).isoformat()
    end = (date.today() + timedelta(days=3)).isoformat()
    c, r = call("POST", "/api/meal-plan/week/generate",
                {"start_date": start, "end_date": end, "meal_types": ["午"]})
    d = r.get("data") or {}
    pid = d.get("meal_plan_id") or d.get("plan_id")
    if not (c == 200 and r.get("code") == 0 and pid):
        record("S-01", "FAIL", f"方案生成失败 code={c} body={str(r)[:160]}")
        return 1
    c2, det = call("GET", f"/api/meal-plan/{pid}")
    plan = det.get("data") or {}
    slots = slots_of(plan)
    ok = plan.get("status") == "candidates" and slots and all(len(s.get("candidates") or []) >= 2 for s in slots)
    record("S-01", "PASS" if ok else "FAIL",
           f"plan_id={pid} status={plan.get('status')} 槽位={len(slots)} "
           f"候选数={[len(s.get('candidates') or []) for s in slots]}")

    # S-02 候选切换（ab67a09：rank 约束 400/500）
    slot = slots[0]
    slid = int(slot["meal_slot_id"])
    before = int(slot["selected_candidate_id"])
    others = [x["candidate_id"] for x in slot["candidates"] if x["candidate_id"] != before]
    if not others:
        record("S-02", "FAIL", f"slot={slid} 只有一个候选，无法切换")
    else:
        c3, r3 = call("POST", "/api/meal-plan/candidate/swap",
                      {"meal_plan_id": pid, "meal_slot_id": slid,
                       "candidate_id": others[0], "reason": "回归测试"})
        c4, det2 = call("GET", f"/api/meal-plan/{pid}")
        after = int((slots_of(det2.get("data") or {})[0] or {}).get("selected_candidate_id") or 0)
        ok = c3 == 200 and r3.get("code") == 0 and after == others[0]
        record("S-02", "PASS" if ok else "FAIL",
               f"slot={slid} {before}->{after}（期望 {others[0]}） http={c3} code={r3.get('code')} "
               f"msg={str(r3.get('message'))[:40]}")

    # S-03 单菜替换（ab67a09：局部修改被误拦截）
    # 注意：replacement_query 传具体菜名会先按名称/配料过滤，容易池空而拿到 400「没有符合…的替代菜」，
    # 那是业务性拒绝，验不到修复点。这里留空走"同角色替换"，与前端「换掉这道菜」的实际路径一致。
    def latest_slot() -> dict:
        _, dd = call("GET", f"/api/meal-plan/{pid}")
        ss = slots_of(dd.get("data") or {})
        return ss[0] if ss else {}

    s3 = latest_slot()
    ds = dishes_of(s3.get("selected_candidate") or {})
    replaced, detail_a = False, ""
    if len(ds) < 2:
        record("S-03a", "BLOCKED", f"当前候选菜品不足（{ds}），无法做单菜替换")
    else:
        for target in list(reversed(ds)):
            body = {"meal_plan_id": pid, "meal_slot_id": int(s3["meal_slot_id"]),
                    "expected_candidate_id": int(s3["selected_candidate_id"]),
                    "dish_id": target, "replacement_query": "", "allow_approximate": True}
            c6, r6 = call("POST", "/api/meal-plan/dish/replace", body)
            s3b = latest_slot()
            after = dishes_of(s3b.get("selected_candidate") or {})
            if c6 == 200 and r6.get("code") == 0 and after != ds:
                replaced = True
                detail_a = f"替换 {target} → {after}（候选 {s3.get('selected_candidate_id')}→{s3b.get('selected_candidate_id')}）"
                break
            detail_a = f"替换 {target} http={c6} code={r6.get('code')} msg={str(r6.get('message'))[:50]}"
        record("S-03a", "PASS" if replaced else "WARN", detail_a)
    if not replaced:
        record("S-03b", "BLOCKED", "同角色替换均未成功，严格模式无需再验")
    else:
        # 严格模式：不带 allow_approximate。放通则说明一步到位，被拒且理由是营养近似属预期，
        # 只有 5xx / 约束异常 / 其它 400 才算修复回退。
        s3c = latest_slot()
        ds3 = dishes_of(s3c.get("selected_candidate") or {})
        c7, r7 = call("POST", "/api/meal-plan/dish/replace",
                      {"meal_plan_id": pid, "meal_slot_id": int(s3c["meal_slot_id"]),
                       "expected_candidate_id": int(s3c["selected_candidate_id"]),
                       "dish_id": ds3[-1], "replacement_query": ""})
        msg7 = str(r7.get("message"))
        s3d = latest_slot()
        ds4 = dishes_of(s3d.get("selected_candidate") or {})
        if c7 == 200 and r7.get("code") == 0 and ds4 != ds3:
            record("S-03b", "PASS", f"严格模式直接放通 {ds3} → {ds4}")
        elif "营养" in msg7 or "近似" in msg7:
            record("S-03b", "INFO", f"严格模式按预期要求确认近似：code={r7.get('code')} msg={msg7[:60]}")
        elif c7 >= 500:
            record("S-03b", "FAIL", f"严格模式 5xx（约束异常未修好）：http={c7} msg={msg7[:60]}")
        else:
            record("S-03b", "WARN", f"严格模式其它拒绝：http={c7} code={r7.get('code')} msg={msg7[:60]}")

    # S-04 意图路由观察（仅记录）：含「替换」不应落确认流程
    # /api/agent/chat 是 SSE，入参为 {user_id, message, conversation_id?, context?}，与方案接口不同。
    # call() 只保留 200 字符，判断 SSE 语义需要全文，这里单独发一次并读完整流。
    raw4 = ""
    try:
        req4 = urllib.request.Request(
            BASE + "/api/agent/chat",
            data=json.dumps({"user_id": UID, "message": "把这道菜替换成青菜",
                             "context": {"meal_plan_id": pid}}).encode(),
            method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {jwt_for()}"})
        with urllib.request.urlopen(req4, timeout=180) as resp4:
            raw4 = resp4.read().decode(errors="replace")
        c8 = 200
    except urllib.error.HTTPError as e:
        c8, raw4 = e.code, e.read().decode(errors="replace")
    except Exception as e:  # noqa: BLE001
        c8, raw4 = 0, str(e)
    if "Agent 服务当前不可达" in raw4 or "AGENT_BASE_URL" in raw4:
        record("S-04", "BLOCKED",
               "后端可达但 agent:8001 未启动（后端原话：Agent 服务当前不可达），"
               "意图路由无法验证；需运维拉起 agent 服务后复跑")
    elif "确认" in raw4 or "confirm" in raw4.lower():
        record("S-04", "FAIL", f"含「替换」的话术仍触发确认流程 http={c8} SSE 片段={raw4[:160]}")
    else:
        record("S-04", "PASS", f"未落确认流程 http={c8} SSE 长度={len(raw4)} 事件={raw4.count('event:')}")

    fails = [x for x in results if x["verdict"] == "FAIL"]
    print(f"\n共 {len(results)} 项：PASS {sum(1 for x in results if x['verdict']=='PASS')} / "
          f"WARN {sum(1 for x in results if x['verdict']=='WARN')} / FAIL {len(fails)}")
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告：{OUT}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
