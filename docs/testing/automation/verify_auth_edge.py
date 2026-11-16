"""鉴权透传修复（af488c1）评审项 P0/P1/P2 的黑盒+静态核查。

用法：
    python docs/testing/automation/verify_auth_edge.py            # 只跑静态项（不需要隧道）
    LIVE_BASE_URL=https://... python docs/testing/automation/verify_auth_edge.py   # 静态 + 在线项

说明：
- P0 并发串号：静态检查 agent/backend_client.py 是否仍用模块级 _token；
  在线并发只作佐证，不替代代码修复。
- P1 身份源：签 sub=A 的 token、body 填 user_id=B，观察后端是否拒绝或错位；
  2xx 不代表通过——会话/方案归属须 DB（diet_ro）复核。
- P2 Bearer 边界：标准头必须 200；非法/异常大小写头记录实际状态供人工判定。
- token 使用仓库默认 secret 离线签发，不落报告、不打印明文。
"""
from __future__ import annotations

import json
import os
import sys
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
BASE = os.getenv("LIVE_BASE_URL", "").rstrip("/")
SECRET = "change-me-in-production"
results: list[dict] = []


def record(cid: str, title: str, passed: bool | None, note: str) -> None:
    results.append({"id": cid, "title": title, "pass": passed, "note": note})
    mark = "PASS" if passed is True else ("FAIL" if passed is False else "CHECK")
    print(f"[{mark}] {cid} {title} -> {note}")


def jwt_for(sub: str) -> str:
    import jwt
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": sub, "iat": now, "exp": now + timedelta(hours=24)}, SECRET, algorithm="HS256")


def http(path: str, token: str | None, method: str = "GET", body: dict | None = None,
         header: str | None = None, timeout: int = 30) -> tuple[int | None, str]:
    headers = {"Content-Type": "application/json"}
    if header is not None:
        headers["Authorization"] = header
    elif token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")[:200]
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:120]}"


def static_p0() -> None:
    src = (REPO / "agent" / "backend_client.py").read_text(encoding="utf-8")
    global_token = "_token: str | None = None" in src and "global _token" in src
    record("P0-static", "agent 全局 _token 并发串号（源码）", not global_token,
           "模块级 global _token 仍在，须改请求级参数或 contextvars" if global_token else "未见模块级全局 token")


def online_p0() -> None:
    ta, tb = jwt_for("AUTH-E2E-A"), jwt_for("AUTH-E2E-B")
    seen: list[tuple[str, int | None, str]] = []

    def chat(sub: str, token: str, tag: str) -> None:
        st, raw = http("/api/agent/chat", token, "POST",
                       {"user_id": sub, "message": "我最近老掉发，可能缺什么营养？"}, timeout=90)
        bad = "event: error" in raw or "error" in raw[:200].lower()
        seen.append((tag, st, f"status={st} bytes={len(raw)} error_frame={bad}"))

    t1 = threading.Thread(target=chat, args=("AUTH-E2E-A", ta, "A"))
    t2 = threading.Thread(target=chat, args=("AUTH-E2E-B", tb, "B"))
    t1.start(); t2.start(); t1.join(); t2.join()
    detail = " | ".join(f"{tag}:{note}" for tag, _, note in sorted(seen))
    ok = all(st == 200 for _, st, _ in seen) and all("error_frame=False" in n for _, _, n in seen)
    record("P0-online", "双用户并发 SSE 冒烟（仅佐证）", ok, detail + "；黑盒不能证明无串号，须代码审查确认")


def online_p1() -> None:
    ta = jwt_for("AUTH-E2E-A")
    st, raw = http("/api/agent/chat", ta, "POST",
                   {"user_id": "AUTH-E2E-B", "message": "帮我配今天的三餐"}, timeout=90)
    rejected = st in (400, 401, 403)
    note = f"sub=A / body.user_id=B -> HTTP {st}; " + ("已拒绝" if rejected else "未拒绝")
    if not rejected:
        note += "；须用 diet_ro 查会话/方案归属（会话是否存到 B、方案是否写到 A），不能凭 200 判通过"
    record("P1", "body user_id 与 token sub 错位", rejected, note)


def online_p2() -> None:
    tok = jwt_for("AUTH-E2E-A")
    cases = [
        ("标准 Bearer", "Bearer " + tok, 200),
        ("Bearer 无空格", "Bearer", None),
        ("前导空格", "  Bearer " + tok, None),
        ("小写 bearer", "bearer " + tok, None),
    ]
    for name, header, expected in cases:
        st, _ = http("/api/profile", None, header=header)
        ok = (st == expected) if expected else None
        record("P2-" + name, name, ok, f"HTTP {st}" + ("" if expected else "（异常格式，供人工判定）"))


def main() -> int:
    static_p0()
    if not BASE:
        print("\n未设 LIVE_BASE_URL，跳过在线项。设置后重跑可覆盖 P1/P2 与 P0 冒烟。")
    else:
        print(f"\n== 在线核查 {BASE} ==")
        online_p0()
        online_p1()
        online_p2()
    out = HERE / "auth_edge_results.json"
    out.write_text(json.dumps({"time": datetime.now().isoformat(), "base": BASE or None,
                               "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    failed = sum(r["pass"] is False for r in results)
    print(f"\n共 {len(results)} 项：FAIL {failed} / CHECK {sum(r['pass'] is None for r in results)}")
    print(f"报告：{out}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
