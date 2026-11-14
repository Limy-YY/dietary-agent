"""契约 v1.2 解析与校验器（测试岗 · 联调前自动门禁）。

口径来源：
- REST 统一包裹 {code, message, data}（backend/app/core/response.py）
- 错误码分段 0 / 10xx / 20xx / 3001（backend/app/core/errors.py）
- SSE 事件（docs：Agent 输出契约 v1.2；backend/app/routers/chat.py 现为占位实现，
  仅 session/message/done，artifact 与 clarify 尚未接线——本模块按 v1.2 全集解析，
  供前端 mock 与后端补齐后回归共用）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

# v1.2 SSE 事件全集
EVENT_NAMES = {"session", "message", "artifact", "clarify", "done", "error"}

# 允许出现在 data 里的错误码（与 errors.py 一致）
ERROR_CODES = {1001, 1002, 1003, 1004, 2001, 2002, 2003, 2004, 3001}


@dataclass
class SseEvent:
    name: str
    data: dict


@dataclass
class ContractViolation:
    where: str
    detail: str


@dataclass
class CheckResult:
    violations: list[ContractViolation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations


def parse_sse(raw: str) -> list[SseEvent]:
    """把 SSE 原始文本解析为事件列表；空行分隔帧，data 必须是合法 JSON。"""
    events: list[SseEvent] = []
    name = ""
    data_lines: list[str] = []

    def _flush():
        nonlocal name, data_lines
        if not name and not data_lines:
            return
        raw_data = "\n".join(data_lines)
        try:
            payload = json.loads(raw_data) if raw_data else {}
        except json.JSONDecodeError as e:
            raise ValueError(f"data 不是合法 JSON: {e}") from e
        events.append(SseEvent(name=name, data=payload))
        name, data_lines = "", []

    for line in raw.splitlines():
        if line.startswith("event:"):
            name = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:"):].strip())
        elif line.strip() == "":
            _flush()
    _flush()
    return events


def unwrap_response(payload: dict) -> tuple[int, str, object]:
    """REST 出参解包：返回 (code, message, data)。缺键直接抛 KeyError，由调用方判定。"""
    return int(payload["code"]), str(payload["message"]), payload.get("data")


def check_stream(events: list[SseEvent]) -> CheckResult:
    """校验一次对话流：事件名合法、首帧 session、收尾 done、clarify 必须追问、error 必须带合法错误码。"""
    r = CheckResult()
    if not events:
        r.violations.append(ContractViolation("stream", "事件流为空"))
        return r

    for i, ev in enumerate(events):
        tag = f"event[{i}]"
        if ev.name not in EVENT_NAMES:
            r.violations.append(ContractViolation(tag, f"未知事件名 {ev.name!r}"))
            continue
        if ev.name == "clarify":
            q = ev.data.get("question") or ev.data.get("needs_clarification")
            if not q:
                r.violations.append(
                    ContractViolation(tag, "clarify 事件必须携带 question / needs_clarification，否则前端无从追问"))
        if ev.name == "error":
            code = ev.data.get("code")
            if code not in ERROR_CODES:
                r.violations.append(ContractViolation(tag, f"error 事件错误码非法: {code!r}"))
        if ev.name == "message":
            if "content" not in ev.data:
                r.violations.append(ContractViolation(tag, "message 事件缺 content 字段"))

    if events[0].name != "session":
        r.violations.append(ContractViolation("stream", f"首帧必须是 session，实际是 {events[0].name!r}"))
    if events[-1].name != "done":
        r.violations.append(ContractViolation("stream", f"收尾必须是 done，实际是 {events[-1].name!r}"))
    return r


def check_response(payload: dict) -> CheckResult:
    """校验一个 REST 出参：{code,message,data} 三键齐全、code 合法、非 0 时 data 为 null。"""
    r = CheckResult()
    for k in ("code", "message"):
        if k not in payload:
            r.violations.append(ContractViolation("response", f"统一包裹缺 {k} 键"))
    code = payload.get("code")
    if not isinstance(code, int):
        r.violations.append(ContractViolation("response", f"code 必须是 int，实际 {type(code).__name__}"))
    elif code != 0 and code not in ERROR_CODES:
        r.violations.append(ContractViolation("response", f"code={code} 不在错误码表"))
    if isinstance(code, int) and code != 0 and payload.get("data") is not None:
        r.violations.append(ContractViolation("response", f"code={code} 失败时 data 应为 null"))
    return r
