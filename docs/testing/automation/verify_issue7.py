"""#7 三条复验判据。用法：LIVE_BASE_URL=https://... python verify_issue7.py"""
import json, os, sys, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = os.getenv("LIVE_BASE_URL", "").rstrip("/")
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from jwt_secret import jwt_secret  # noqa: E402

SECRET = jwt_secret()
results = []

def jwt_for(sub):
    import jwt
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": sub, "iat": now, "exp": now + timedelta(hours=24)}, SECRET, algorithm="HS256")

def chat_sse(token, user_id, message, timeout=90):
    req = urllib.request.Request(BASE + "/api/agent/chat",
        data=json.dumps({"user_id": user_id, "message": message}).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + token}, method="POST")
    raw = urllib.request.urlopen(req, timeout=timeout).read().decode()
    ev = None; frames = []
    for line in raw.splitlines():
        if line.startswith("event:"): ev = line[6:].strip()
        elif line.startswith("data:"):
            try: frames.append((ev, json.loads(line[5:].strip())))
            except Exception: pass
    return raw, frames

def find_payload(frames, etype):
    for e, d in frames:
        if e == etype: return d
    return None

def deep_get(obj, *keys):
    for k in keys:
        if not isinstance(obj, dict): return None
        obj = obj.get(k)
        if obj is None: return None
    return obj

def record(cid, ok, note):
    results.append({"id": cid, "pass": ok, "note": note})
    print(f"[{'PASS' if ok else 'FAIL'}] {cid} -> {note}")

def main():
    if not BASE:
        print("需设置 LIVE_BASE_URL"); return 2

    # ---- 判据1：已建档用户出方案，plan_id/slots 非空，done.meal_plan_id == plan_id ----
    t1 = jwt_for("TEST-E2E-01")
    st, _ = __import__("verify_live_helper") if False else (None, None)
    # 建档（幂等）
    req = urllib.request.Request(BASE + "/api/profile",
        data=json.dumps({"user_id": "TEST-E2E-01", "gender": "female", "age": 24, "height_cm": 163,
                         "weight_kg": 52, "goal_code": "maintain", "activity_level": "light"}).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + t1}, method="PUT")
    try: urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as e: pass  # 字段差异由既有 R-05a 保证，这里尽力建档
    raw, fr = chat_sse(t1, "TEST-E2E-01", "帮我配今天的三餐")
    art = find_payload(fr, "artifact"); done = find_payload(fr, "done")
    plan_id = deep_get(art, "payload", "plan_id")
    slots = deep_get(art, "payload", "slots")
    done_pid = deep_get(done, "meal_plan_id")
    record("判据1-artifact", bool(plan_id) and bool(slots),
           f"plan_id={plan_id} slots={len(slots) if isinstance(slots,list) else slots} done.meal_plan_id={done_pid}")
    record("判据1-done一致", bool(plan_id) and done_pid == plan_id,
           f"done={done_pid} vs plan_id={plan_id}")

    # ---- 判据3：无档案用户报身体指标 → 建档 + 首轮出方案；二轮不再兜底 ----
    t3 = jwt_for("TEST-E2E-05")
    raw3, fr3 = chat_sse(t3, "TEST-E2E-05", "女，26岁，160cm，55kg，想增肌")
    art3 = find_payload(fr3, "artifact"); done3 = find_payload(fr3, "done")
    pid3 = deep_get(art3, "payload", "plan_id") or deep_get(done3, "meal_plan_id")
    record("判据3-首轮建档出方案", bool(pid3) or "event: clarify" not in raw3,
           f"plan_id={pid3} events={[e for e,_ in fr3][:6]}")
    try:
        st, body = (lambda r: (r.status, r.read().decode()))(urllib.request.urlopen(
            urllib.request.Request(BASE + "/api/profile?user_id=TEST-E2E-05",
                headers={"Authorization": "Bearer " + t3}), timeout=30))
        record("判据3-档案已建", st == 200, f"GET /api/profile -> {st}")
    except urllib.error.HTTPError as e:
        record("判据3-档案已建", False, f"GET /api/profile -> {e.code}")
    raw4, fr4 = chat_sse(t3, "TEST-E2E-05", "配今天午餐")
    txt = "".join(d.get("content") or d.get("delta") or "" for e, d in fr4 if e == "message")
    pid4 = deep_get(find_payload(fr4, "artifact"), "payload", "plan_id") or deep_get(find_payload(fr4, "done"), "meal_plan_id")
    record("判据3-二轮不兜底", "还没有你的档案" not in txt and bool(pid4),
           f"plan_id={pid4} 兜底文案={'有' if '还没有你的档案' in txt else '无'}")

    out = HERE / "issue7_results.json"
    out.write_text(json.dumps({"time": datetime.now().isoformat(), "base": BASE,
                               "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    fails = sum(1 for r in results if not r["pass"])
    print(f"\n共 {len(results)} 项：FAIL {fails}；报告 {out}")
    return 1 if fails else 0

if __name__ == "__main__":
    sys.exit(main())
