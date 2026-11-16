"""G-D 真实接口回归（联调地址可复跑）。

用法：
    LIVE_BASE_URL=https://... python docs/testing/automation/verify_live.py

token 由 app/config.py 的默认 JWT_SECRET 离线签发（与后端 .env 未覆盖时一致）；
如需指定：设置 LIVE_TOKEN 环境变量。明文 token 不落报告、不打印。

判据来源：联调回归清单.md G-D（R-01~R-12）+ docs/联调环境说明.md 三写判据。
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = os.getenv("LIVE_BASE_URL", "").rstrip("/")
USER = "TEST-E2E-01"
HERE = Path(__file__).resolve().parent


def token() -> str:
    env = os.getenv("LIVE_TOKEN")
    if env:
        return env
    import jwt
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": USER, "iat": now, "exp": now + timedelta(minutes=1440)},
        "change-me-in-production",
        algorithm="HS256",
    )


TOKEN = token()
results: list[dict] = []


def call(name: str, method: str, path: str, body: dict | None = None,
         want: int = 200, auth: bool = True, sse: bool = False) -> dict | None:
    url = BASE + path
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = f"Bearer {TOKEN}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    rec = {"id": name, "method": method, "path": path, "status": None, "pass": False, "note": ""}
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            rec["status"] = r.status
            raw = r.read().decode("utf-8", errors="replace")
            rec["pass"] = r.status == want
            if sse:
                frames = [ln[6:].strip() for ln in raw.splitlines() if ln.startswith("data:")]
                rec["note"] = f"sse_frames={len(frames)}"
            else:
                payload = json.loads(raw)
                rec["note"] = f"code={payload.get('code')}" if isinstance(payload, dict) else f"type={type(payload).__name__}"
                if r.status == want and isinstance(payload, dict) and payload.get("code") not in (0, None):
                    rec["pass"] = False
                    rec["note"] += " (business code != 0)"
    except urllib.error.HTTPError as e:
        rec["status"] = e.code
        rec["note"] = f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:120]}"
    except Exception as e:
        rec["note"] = f"{type(e).__name__}: {str(e)[:120]}"
    results.append(rec)
    print(f"[{'PASS' if rec['pass'] else 'FAIL'}] {name} {method} {path} -> {rec['status']} {rec['note']}")
    return rec


def main() -> int:
    print(f"== G-D 真实接口回归 == {BASE} user={USER}")
    call("R-01", "GET", "/api/health", auth=False)
    call("R-02", "GET", "/api/ingredients/search?q=" + urllib.parse.quote("鸡胸肉"))
    call("R-03", "GET", "/api/dishes/search?page=1&page_size=5")
    # 菜式口径：/api/ingredients/search 只返回 food_id（string），而 calc 的食材口径要 core.ingredient
    # 的 bigint ingredient_id，两者不能直接对接；故本门禁用 /api/dishes/search 返回的 dish_id 走菜式口径。
    call("R-04", "POST", "/api/calc/nutrition",
         {"target_type": "dish", "items": [{"dish_id": "DISH-001", "servings": 1}], "include_micro": True})

    # 三写·档案写（用固定测试档案，返回 200 即已落库；库内 SELECT 见联调环境说明.md）
    call("R-05a", "PUT", "/api/profile",
         {"user_id": USER, "gender": "女", "age": 26, "height_cm": 160, "weight_kg": 55,
          "goal_code": "digestive_health"})
    call("R-05b", "GET", "/api/profile")

    call("R-06", "POST", "/api/nutrition/analysis", {"meal_plan_id": 10, "window_days": 7})
    call("R-07a", "GET", "/api/condition-rules/catalog?page=1&page_size=5")
    call("R-07b", "GET", "/api/condition-rules/production")
    call("R-07c", "GET", "/api/conditions/catalog")
    call("R-07d", "GET", "/api/conditions")

    # 三写·方案写（生成后天起的 7 天方案；start/end 用固定日期保证可复跑）
    call("R-08", "POST", "/api/meal-plan/week/generate",
         {"start_date": "2026-11-17", "end_date": "2026-11-23",
          "meal_types": ["早", "午", "晚"], "candidates_per_slot": 3})
    call("R-09a", "GET", "/api/meal-plan/current")
    call("R-09b", "GET", "/api/meal-plan/list?page=1&page_size=5")

    # 三写·对话写（后端 agent 服务未起时预期降级，但 conversation/message 仍会写）
    call("R-12", "POST", "/api/agent/chat",
         {"user_id": USER, "message": "中午吃什么比较好"}, sse=True)

    out = HERE / "live_results.json"
    out.write_text(json.dumps({"base": BASE, "time": datetime.now().isoformat(), "results": results},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    passed = sum(r["pass"] for r in results)
    print(f"\n共 {len(results)} 项：PASS {passed} / FAIL {len(results) - passed}")
    print(f"报告：{out}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
