"""样例断言（G-C 门禁）：对 backend/samples 两份真实响应样例做结构与字段断言。

用法：
    python docs/testing/automation/assert_samples.py        # 退出码 0 = 全过

覆盖：
- api-14_agent_chat_sample.sse.txt：SSE 恰 4 帧（message×2 → artifact → done）、
  done 帧无 session 字段、artifact 为 meal_card 且含 plan_id/title。
- api-25_nutrition_analysis_sample.json：REST {code,message,data} 包裹、
  summary.daily_trend 非空、macro 达标率含 range、sources 非空。

口径：《Agent 输出契约 v1.2》；样例由后端交付（c55ecd0），测试岗验收留痕
commit comment 210089421。后端更新样例后重跑本脚本即可判定结构回归。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SAMPLES = HERE / ".." / ".." / ".." / "backend" / "samples"

FAILS: list[str] = []
CHECKS = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def parse_sse(text: str) -> list[tuple[str, dict]]:
    """按空行分帧，解析 event/data；data 必须是合法 JSON。"""
    frames: list[tuple[str, dict]] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        block = block.strip()
        if not block:
            continue
        ev = None
        data_raw = None
        for line in block.splitlines():
            if line.startswith("event:"):
                ev = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_raw = line.split(":", 1)[1].strip()
        if ev is None or data_raw is None:
            raise ValueError(f"帧缺 event 或 data 行: {block[:60]!r}")
        frames.append((ev, json.loads(data_raw)))
    return frames


def assert_sse_sample() -> None:
    p = SAMPLES / "api-14_agent_chat_sample.sse.txt"
    frames = parse_sse(p.read_text(encoding="utf-8"))

    check("SSE 帧数恰为 4", len(frames) == 4, f"实际 {len(frames)}")
    seq = [ev for ev, _ in frames]
    check("帧序 message×2 → artifact → done",
          seq == ["message", "message", "artifact", "done"], f"实际 {seq}")

    for i, (ev, data) in enumerate(frames[:2], 1):
        check(f"message#{i} type=text 且 content 非空",
              data.get("type") == "text" and isinstance(data.get("content"), str)
              and len(data["content"]) > 0, f"data={data}")

    ev, art = frames[2]
    check("artifact type=meal_card", art.get("type") == "meal_card", f"data={art}")
    payload = art.get("payload") or {}
    check("artifact payload 含 plan_id 与 title",
          bool(payload.get("plan_id")) and bool(payload.get("title")), f"payload={payload}")

    ev, done = frames[3]
    check("done 帧无 session 字段", "session" not in done, f"data={done}")
    check("done 帧含 conversation_id 与 finish_reason",
          "conversation_id" in done and bool(done.get("finish_reason")), f"data={done}")


def assert_nutrition_sample() -> None:
    p = SAMPLES / "api-25_nutrition_analysis_sample.json"
    d = json.loads(p.read_text(encoding="utf-8"))

    check("REST 统一包裹含 code/message/data",
          all(k in d for k in ("code", "message", "data")), f"top keys={list(d)}")
    check("code=0", d.get("code") == 0, f"code={d.get('code')}")

    data = d["data"]
    summary = data.get("summary") or {}
    trend = summary.get("daily_trend")
    check("summary.daily_trend 非空列表", isinstance(trend, list) and len(trend) > 0,
          f"daily_trend={type(trend).__name__}")
    if isinstance(trend, list) and trend:
        keys = set(trend[0])
        # 字段名以交付样例为准（calories/fat_g/carb_g/protein_g/micro/status…）
        check("daily_trend 行含 calories 与 status 字段",
              {"calories", "status"} <= keys, f"keys={sorted(keys)}")
        check("daily_trend 行含三大宏量营养字段",
              {"fat_g", "carb_g", "protein_g"} <= keys, f"keys={sorted(keys)}")

    macro = (summary.get("achievement") or {}).get("macro") or {}
    for k in ("fat_pct", "carb_pct", "protein_pct"):
        cell = macro.get(k) or {}
        check(f"macro.{k} 达标率含 value_pct/level/range[2]",
              isinstance(cell.get("value_pct"), (int, float))
              and cell.get("level") in ("ok", "low", "high", "unknown")
              and isinstance(cell.get("range"), list) and len(cell["range"]) == 2,
              f"cell={cell}")

    check("data.sources 非空", bool(data.get("sources")), "sources 为空")
    check("data_quality_notes 为列表", isinstance(summary.get("data_quality_notes"), list))


def main() -> int:
    print(f"== G-C 样例断言 == samples 目录: {SAMPLES.resolve()}")
    assert_sse_sample()
    assert_nutrition_sample()
    print(f"\n共 {CHECKS} 项：PASS {CHECKS - len(FAILS)} / FAIL {len(FAILS)}")
    if FAILS:
        print("未过项：" + "、".join(FAILS))
        return 1
    print("退出码 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
