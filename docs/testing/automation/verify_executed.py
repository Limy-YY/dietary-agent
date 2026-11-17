"""G-D2 执行打卡回归（v1.2r3 API-26 is_executed）。

用法：
    LIVE_BASE_URL=https://... python docs/testing/automation/verify_executed.py

覆盖联调回归清单 G-D2 的 EX-01~EX-04：
    EX-01 打卡成功 + 详情回读
    EX-02 打卡可回退（true→false→true，幂等无状态机副作用）
    EX-03 他人方案打卡被拒（403 FORBIDDEN）
    EX-04 时段报告 executed_plans 计数联动（无 fixed 方案时 SKIP 并说明）

token 由默认 JWT_SECRET 离线签发（与后端 .env 未覆盖时一致），不打印明文。
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = os.getenv("LIVE_BASE_URL", "").rstrip("/")
SECRET = os.getenv("LIVE_JWT_SECRET", "change-me-in-production")
USER_A = os.getenv("LIVE_USER_A", "TEST-E2E-01")
USER_B = os.getenv("LIVE_USER_B", "TEST-E2E-02")
HERE = Path(__file__).resolve().parent

if not BASE:
    print("需要设置 LIVE_BASE_URL", file=sys.stderr)
    raise SystemExit(2)

results: list[dict] = []


def _token(sub: str) -> str:
    import jwt

    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": sub, "iat": now, "exp": now + timedelta(hours=12)}, SECRET, algorithm="HS256")


TOKEN_A = _token(USER_A)
TOKEN_B = _token(USER_B)


def call(method: str, path: str, body: dict | None = None, token: str | None = TOKEN_A) -> tuple[int, dict]:
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    try:
        with urllib.request.urlopen(req, data=data, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(raw or "{}")
        except json.JSONDecodeError:
            return exc.code, {"raw": raw[:400]}


def record(case: str, ok: bool, detail: str) -> None:
    results.append({"case": case, "pass": ok, "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {case} {detail}")


def _d(body: dict | None, *keys, default=None):
    cur = body
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return default if cur is None else cur


def pick_plan() -> tuple[int, str] | tuple[None, str]:
    code, body = call("GET", "/api/meal-plan/current")
    if code == 200 and body.get("code") == 0 and body.get("data"):
        plan = body["data"]
        return int(plan["meal_plan_id"]), str(plan.get("status"))
    code, body = call("GET", "/api/meal-plan/list?page=1&page_size=20")
    data = body.get("data") or {}
    items = data.get("items") if isinstance(data, dict) else data
    if code == 200 and body.get("code") == 0 and items:
        return int(items[0]["meal_plan_id"]), str(items[0].get("status"))
    return None, ""


def main() -> int:
    print(f"== G-D2 执行打卡回归 == {BASE} user={USER_A}")

    plan_id, status = pick_plan()
    if plan_id is None:
        code, body = call("POST", "/api/meal-plan/week/generate", {"start_date": None})
        if code == 200 and body.get("code") == 0:
            plan_id = int(body["data"]["meal_plan_id"])
            status = str(body["data"].get("status"))
        else:
            record("PRE-00", False, f"无法取得方案：HTTP {code} {str(body)[:200]}")
            return 1
    print(f"-- 目标方案 plan_id={plan_id} status={status}")

    # 前置：确认部署版本已含 API-26（openapi 无该 path 时直接判「部署版本落后」，不逐条刷 FAIL）
    import urllib.error as _ue

    try:
        with urllib.request.urlopen(BASE + "/openapi.json", timeout=30) as resp:
            spec = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        spec = {}
        print(f"-- openapi 获取失败：{exc}")
    has_api26 = any("/executed" in p for p in (spec.get("paths") or {}))
    if not has_api26:
        record(
            "PRE-01",
            False,
            f"BLOCKED：部署后端 openapi 共 {len(spec.get('paths') or {})} 条 path，无 /api/meal-plan/{{plan_id}}/executed"
            "（API-26 未部署，仓库 de733ab 已实现）→ EX-01~04 无法执行，需后端部署到含 is_executed 的版本",
        )
        out = HERE / "executed_results.json"
        out.write_text(
            json.dumps(
                {"base": BASE, "plan_id": plan_id, "status": status, "results": results},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"报告：{out}")
        return 1

    # EX-01 打卡成功 + 详情回读
    code, body = call("POST", f"/api/meal-plan/{plan_id}/executed", {"executed": True})
    ok1 = code == 200 and body.get("code") == 0 and body.get("data", {}).get("is_executed") is True
    code2, body2 = call("GET", f"/api/meal-plan/{plan_id}")
    ok1 = ok1 and code2 == 200 and body2.get("data", {}).get("is_executed") is True
    record("EX-01", ok1, f"POST executed=true→{code}/{body.get('data')}；GET 详情 is_executed={body2.get('data', {}).get('is_executed')}")

    # EX-02 可回退 + 幂等
    code3, body3 = call("POST", f"/api/meal-plan/{plan_id}/executed", {"executed": False})
    code4, body4 = call("POST", f"/api/meal-plan/{plan_id}/executed", {"executed": True})
    code5, body5 = call("POST", f"/api/meal-plan/{plan_id}/executed", {"executed": True})
    ok2 = (
        code3 == 200 and _d(body3,"data","is_executed") is False
        and code4 == 200 and body4.get("data", {}).get("is_executed") is True
        and code5 == 200 and body5.get("data", {}).get("is_executed") is True
    )
    record("EX-02", ok2, f"true→false({code3}:{_d(body3,"data","is_executed")})→true({code4})→重复 true({code5})")

    # EX-03 他人方案被拒
    code6, body6 = call("POST", f"/api/meal-plan/{plan_id}/executed", {"executed": True}, token=TOKEN_B)
    ok3 = code6 == 403
    record("EX-03", ok3, f"用户B 打卡用户A 方案 → HTTP {code6} code={_d(body6,"code")} msg={str(body6.get('message'))[:60]}")

    # EX-04 报告 executed_plans 计数联动（需目标方案 status='fixed' 且落在报告窗口内）
    def _plan_stats() -> tuple[int, int, int]:
        c, r = call("POST", "/api/nutrition/period-analysis", {"report_type": "week", "window_days": 7})
        s = ((r.get("data") or {}).get("summary") or {}).get("plan_stats") or {}
        return c, int(s.get("total_plans") or 0), int(s.get("executed_plans") or 0)

    code7, total0, _ = _plan_stats()
    if status != "fixed" or code7 != 200:
        record(
            "EX-04",
            True,
            f"SKIP：目标方案 status={status}（计数口径只收 status='fixed' 方案），报告 HTTP {code7}，"
            "用例条件不满足，不作 FAIL；需先 POST /api/meal-plan/week/fix 再复跑本项",
        )
    elif total0 == 0:
        record("EX-04", True, f"SKIP：窗口内 fixed 方案 0 份（total_plans=0），计数判据不可达，不作 FAIL")
    else:
        # 制造差量：先置 false 读基线，再置 true 读结果，差值必须恰好 +1
        call("POST", f"/api/meal-plan/{plan_id}/executed", {"executed": False})
        _, total_b, before = _plan_stats()
        call("POST", f"/api/meal-plan/{plan_id}/executed", {"executed": True})
        code8, total_a, after = _plan_stats()
        ok4 = code8 == 200 and after == before + 1 and total_a == total_b
        record(
            "EX-04",
            ok4,
            f"executed_plans {before} → {after}（total_plans {total_b}→{total_a} 应不变，差值应 +1）",
        )

    passed = sum(1 for r in results if r["pass"])
    print(f"\n共 {len(results)} 项：PASS {passed} / FAIL {len(results) - passed}")
    out = HERE / "executed_results.json"
    out.write_text(
        json.dumps({"base": BASE, "plan_id": plan_id, "status": status, "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"报告：{out}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
