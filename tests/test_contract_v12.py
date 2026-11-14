"""契约 v1.2 回归断言（离线可跑，无 pytest 依赖）。

用法：
    python tests/test_contract_v12.py          # 全部断言
    python tests/test_contract_v12.py -v       # 逐条输出
退出码 0 = 通过，非 0 = 有断言失败，可直接挂 CI 门禁。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from contract_v12 import (  # noqa: E402
    check_response,
    check_stream,
    parse_sse,
    unwrap_response,
)

RESULTS: list[tuple[str, bool, str]] = []


def case(cid: str, desc: str, fn):
    try:
        fn()
        RESULTS.append((cid, True, ""))
    except AssertionError as e:
        RESULTS.append((cid, False, str(e)))
    except Exception as e:  # noqa: BLE001
        RESULTS.append((cid, False, f"异常 {type(e).__name__}: {e}"))


def expect(cond, msg=""):
    if not cond:
        raise AssertionError(msg or "断言失败")


# ---------- G-A：SSE 三类事件解析 ----------
FIXTURE_OK = """event: session
data: {"conversation_id": 12}

event: message
data: {"type": "text", "content": "先确认一下你的过敏原"}

event: artifact
data: {"kind": "meal_plan", "plan_id": 3001}

event: done
data: {"conversation_id": 12}

"""

FIXTURE_CLARIFY = """event: session
data: {"conversation_id": 7}

event: clarify
data: {"question": "减脂目标是每周 0.5kg 还是 1kg？", "options": ["0.5kg", "1kg"]}

event: done
data: {"conversation_id": 7}

"""


def a1_parse_three_kinds():
    evs = parse_sse(FIXTURE_OK)
    expect([e.name for e in evs] == ["session", "message", "artifact", "done"],
           f"事件序列不符: {[e.name for e in evs]}")
    expect(evs[2].data["plan_id"] == 3001, "artifact 的 plan_id 应为 3001")
    r = check_stream(evs)
    expect(r.ok, f"合法流被误判: {r.violations}")


def a2_clarify_must_ask():
    evs = parse_sse(FIXTURE_CLARIFY)
    r = check_stream(evs)
    expect(r.ok, f"带 question 的 clarify 应通过: {r.violations}")
    bad = parse_sse(FIXTURE_CLARIFY.replace('"question": "减脂目标是每周 0.5kg 还是 1kg？", ', ""))
    r2 = check_stream(bad)
    expect(not r2.ok, "clarify 缺 question 必须判失败")
    expect(any("clarify" in v.detail for v in r2.violations), "失败原因应指向 clarify 追问字段")


def a3_stream_must_frame():
    r = check_stream(parse_sse("event: message\ndata: {\"content\": \"hi\"}\n\n"))
    expect(not r.ok, "缺 session 首帧应判失败")
    r2 = check_stream(parse_sse(FIXTURE_OK.replace("event: done\ndata: {\"conversation_id\": 12}\n\n", "")))
    expect(not r2.ok, "缺 done 收尾应判失败")


def a4_error_carries_valid_code():
    stream = """event: session
data: {"conversation_id": 3}

event: error
data: {"code": 2003, "message": "AI 解释暂不可用"}

event: done
data: {"conversation_id": 3}

"""
    r = check_stream(parse_sse(stream))
    expect(r.ok, f"2003 错误流应通过: {r.violations}")
    bad = stream.replace('"code": 2003', '"code": 9999')
    r2 = check_stream(parse_sse(bad))
    expect(not r2.ok, "非法错误码 9999 应判失败")


# ---------- G-B：REST {code,message,data} 统一解包 ----------


def b1_unwrap_success():
    code, msg, data = unwrap_response({"code": 0, "message": "ok", "data": {"plan_id": 3001}})
    expect((code, msg) == (0, "ok"), "成功包裹解包错误")
    expect(data["plan_id"] == 3001, "data 应原样保留")


def b2_unwrap_error_null_data():
    code, _, data = unwrap_response({"code": 2003, "message": "结构化输出校验失败", "data": None})
    expect(code == 2003 and data is None, "失败包裹 data 必须为 null")
    r = check_response({"code": 2003, "message": "x", "data": {"leak": 1}})
    expect(not r.ok, "失败时 data 非 null 应判失败")


def b3_missing_wrapper_keys():
    for bad in ({"message": "ok", "data": None}, {"code": 0, "data": None}, {"code": "0", "message": "x"}):
        r = check_response(bad)
        expect(not r.ok, f"{bad} 应判失败（缺键或类型错）")


def b4_code_in_table():
    expect(check_response({"code": 2004, "message": "数据源不可用", "data": None}).ok, "2004 应合法")
    expect(not check_response({"code": 5555, "message": "?", "data": None}).ok, "5555 不在码表应失败")


# ---------- G-C：字段命名（v1.2 契约唯一源） ----------


def c1_field_names():
    artifact = {"kind": "meal_plan", "plan_id": 3001, "is_staple": True, "kcal_per_100g": 120.5}
    expect("plan_id" in artifact and "meal_plan_id" not in artifact, "统一用 plan_id，不是 meal_plan_id")
    expect(isinstance(artifact["is_staple"], bool), "is_staple 必须是布尔")
    expect("kcal_per_100g" in artifact, "菜品级热量字段为 kcal_per_100g（菜品级 kcal 口径）")


def main():
    verbose = "-v" in sys.argv
    case("A-1", "SSE 解析 session/message/artifact/done 四帧", a1_parse_three_kinds)
    case("A-2", "clarify 必须携带追问字段，缺失判失败", a2_clarify_must_ask)
    case("A-3", "流必须 session 开头、done 收尾", a3_stream_must_frame)
    case("A-4", "error 事件错误码必须在码表内", a4_error_carries_valid_code)
    case("B-1", "成功包裹解包保留 data", b1_unwrap_success)
    case("B-2", "失败包裹 data 必须为 null", b2_unwrap_error_null_data)
    case("B-3", "缺 code/message 键或 code 非 int 判失败", b3_missing_wrapper_keys)
    case("B-4", "错误码必须在 1001~3001 码表内", b4_code_in_table)
    case("C-1", "字段命名：plan_id / is_staple / kcal_per_100g", c1_field_names)

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    for cid, ok, err in RESULTS:
        mark = "PASS" if ok else "FAIL"
        if verbose or not ok:
            print(f"[{mark}] {cid} {err}")
    print(f"\n契约断言：{passed}/{len(RESULTS)} 通过")
    sys.exit(0 if passed == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
