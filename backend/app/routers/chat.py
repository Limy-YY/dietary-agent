"""Agent 对话接口（API-14 / POST /agent/chat，SSE 流式）。

链路：前端 ←SSE← 本接口 ←SSE← Agent 服务（`agent/main.py`，`AGENT_BASE_URL` 默认 8001）

事件归一（Agent 输出 → 契约 v1.2 §2.7 五事件）
- Agent `message` {delta}          → `message` {type:"text", content: delta}
- Agent `message` {meta:{blocks}}  → `artifact`（仅四类 type，payload 原样下发）
- Agent `done`                     → `done`（补本接口维护的 conversation_id / meal_plan_id）
- Agent `error`                    → `error`

契约 §2.7 只列 message / artifact / clarify / error / done 五类，**不发 `session`**：
conversation_id 由 `done` 下发（前端 chat.js 即从此取）。

Agent 侧仍按 v1 草案输出 nutrition / recipe_detail / sources / medical_hint / anchor / meal_plan
等 block，v1.2 前端已删除这些 type，收到后丢弃并记 warning —— 由 Agent 岗按
`frontend/docs/agent-output-contract.md` 改造 blocks.py；本接口只做事件与 type 的归一，
不伪造字段（meal_slot_id / candidate_id / macro_estimate 等需要真实落库后才成立）。

降级（保证前端不白屏）
- Agent 不可达 / 超时 → 文本兜底 + done(stop)，日志 warning
- Agent 返回非 200 或流中 error → error(2002) + done(error)
- 档案缺失 → 本地先发 clarify，不把空档案丢给 Agent
"""
import json
import logging
import re

import httpx
from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import BizCode, BizError
from app.db import get_db
from app.routers.mealplan import _get_plan, _serialize_plan
from app.schemas.chat import ChatRequest

router = APIRouter(prefix="/agent", tags=["agent"])
logger = logging.getLogger(__name__)

# Agent 不可达时的兜底回复（开发期 Agent 未启动不至于前端白屏）
_PLACEHOLDER_REPLY = (
    "后端通道已连通（会话已创建，消息已记录），但 Agent 服务当前不可达。"
    "请确认 agent/ 服务已在 8001 启动（AGENT_BASE_URL 可配）。"
)

# 建档所需的轻量字段（与契约 §3.3 必填项一致，v1.2 用 gender），clarify 时原样下发
_REQUIRED_PROFILE_FIELDS = ["gender", "age", "height_cm", "weight_kg", "goal_code"]

# 用户直接在对话里报身体指标时，要放行给 Agent 走建档（PUT /api/profile）。
# 不放行的话「档案缺失 → 一律 clarify」会把建档入口堵死，无档案用户永远建档不了。
_PROFILE_HINT_RE = re.compile(
    r"(男|女)|\d{2,3}\s*(?:cm|厘米|CM|公分)|\d{2,3}\s*(?:kg|KG|公斤|斤)|"
    r"(增肌|减脂|减肥|控糖|血糖|维持|养胃|调理|过敏|忌口)",
    re.IGNORECASE,
)


def _looks_like_profile_input(message: str) -> bool:
    """消息里是否带了可用于建档的身体指标/目标（命中 2 项即视为建档意图）。"""
    return len(_PROFILE_HINT_RE.findall(message or "")) >= 2


# Agent block type → 契约 artifact type；未列出的 v1 草案 block 一律丢弃
_ARTIFACT_TYPE_MAP = {
    "meal_card": "meal_card",
    "shopping_list": "shopping_list",
    "report": "nutrition_report",
    "current_plan": "current_plan",
}


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _get_or_create_conversation(req: ChatRequest, db: Session) -> int:
    if req.conversation_id is not None:
        row = db.execute(
            text("SELECT user_id FROM app.conversation WHERE conversation_id = :cid"),
            {"cid": req.conversation_id},
        ).mappings().first()
        if row is None:
            raise BizError(code=BizCode.NOT_FOUND, message=f"会话不存在: {req.conversation_id}")
        if row["user_id"] != req.user_id:
            raise BizError(code=BizCode.FORBIDDEN, message="会话归属校验失败")
        return req.conversation_id

    cid = db.execute(
        text(
            "INSERT INTO app.conversation (user_id, title) VALUES (:uid, :title) "
            "RETURNING conversation_id"
        ),
        {"uid": req.user_id, "title": req.message[:30]},
    ).scalar_one()
    db.commit()
    return cid


def _save_message(conversation_id: int, role: str, content: str, db: Session) -> None:
    """消息落库。流式回复在流结束时整段落库，避免每帧一次 INSERT。"""
    if not content:
        return
    db.execute(
        text(
            "INSERT INTO app.message (conversation_id, role, content, tool_calls) "
            "VALUES (:cid, :role, :content, '[]'::jsonb)"
        ),
        {"cid": conversation_id, "role": role, "content": content},
    )
    db.commit()


def _profile_exists(db: Session, user_id: str) -> bool:
    row = db.execute(
        text("SELECT 1 FROM app.profile WHERE user_id = :uid"), {"uid": user_id}
    ).first()
    return row is not None


def _load_plan_payload(db: Session, plan_id: int, user_id: str) -> dict | None:
    """current_plan 的 payload：复用 API-04 的序列化，保证与 slots 四级出参同构。"""
    try:
        plan = _get_plan(db, plan_id)
    except BizError:
        return None
    if plan.user_id != user_id:
        return None
    return _serialize_plan(plan)


def _parse_agent_sse(resp: httpx.Response):
    """逐帧解析 Agent 的 SSE 流，产出 (event, data)。"""
    event = "message"
    data_lines: list[str] = []
    for line in resp.iter_lines():
        if line == "":
            if data_lines:
                raw = "\n".join(data_lines)
                try:
                    yield event, json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("Agent SSE 帧非 JSON，已丢弃：%s", raw[:120])
                event, data_lines = "message", []
            continue
        if line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].strip())


def _block_to_artifact(block: dict) -> dict | None:
    """单个 Agent block → 契约 artifact；未识别类型返回 None（不伪造、不降级成文本）。"""
    raw_type = block.get("type")
    artifact_type = _ARTIFACT_TYPE_MAP.get(raw_type)
    if artifact_type is None:
        logger.warning(
            "Agent block type=%s 不在 v1.2 四类 artifact 内，已丢弃（待 Agent 岗按输出契约改造）",
            raw_type,
        )
        return None
    # payload 保留 block 原字段，只去掉 type 与 v1 专用标记，避免与 artifact.type 冲突
    payload = {k: v for k, v in block.items() if k not in ("type", "expanded")}
    return {"type": artifact_type, "payload": payload}


def _agent_events(req: ChatRequest, conversation_id: int, token: str | None = None):
    """调用 Agent 服务并产出契约事件。

    yield (event, data)；调用方负责补 conversation_id 与 done。
    Agent 不可达时抛 httpx 的传输异常，由调用方降级。

    token：调用方 JWT 原样透传给 Agent —— Agent 内部还要回调后端 REST
    （档案 / 食材 / 核算 / 生成方案落库），没有它一律 401，会退化成「没有你的档案」。
    """
    settings = get_settings()
    url = settings.AGENT_BASE_URL.rstrip("/") + "/chat"
    body = {
        "user_id": req.user_id,
        "message": req.message,
        "conversation_id": str(conversation_id),
        "token": token,
    }
    timeout = httpx.Timeout(settings.AGENT_TIMEOUT_S, connect=10.0)
    with httpx.Client(timeout=timeout) as client:
        with client.stream("POST", url, json=body) as resp:
            if resp.status_code != 200:
                raise BizError(
                    code=BizCode.AGENT_CALL_FAILED,
                    message=f"Agent 服务返回 HTTP {resp.status_code}",
                )
            for event, data in _parse_agent_sse(resp):
                if event == "message":
                    if data.get("delta"):
                        yield "message", {"type": "text", "content": data["delta"]}
                    blocks = (data.get("meta") or {}).get("blocks") or []
                    for block in blocks:
                        artifact = _block_to_artifact(block) if isinstance(block, dict) else None
                        if artifact:
                            yield "artifact", artifact
                elif event == "error":
                    yield "error", {
                        "code": int(data.get("code") or BizCode.AGENT_CALL_FAILED),
                        "message": data.get("message") or "Agent 流内报错",
                    }
                elif event == "done":
                    # Agent 的 done 只带自己的 conversation_id / message_id，这里不透传
                    continue
                # Agent 侧的其它事件（如有）不在契约内，忽略


@router.post("/chat")
def agent_chat(
    req: ChatRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
) -> StreamingResponse:
    """与营养智能体多轮对话（SSE 流式；会话缺省自动创建）。"""
    token = (
        authorization[7:].strip()
        if authorization and authorization.lower().startswith("bearer ")
        else None
    )
    conversation_id = _get_or_create_conversation(req, db)
    _save_message(conversation_id, "user", req.message, db)

    def _stream():
        finish_reason = "stop"
        meal_plan_id: int | None = None
        assistant_text: list[str] = []

        try:
            if not _profile_exists(db, req.user_id) and not _looks_like_profile_input(req.message):
                # 契约 §2.7：信息不足必须 clarify 追问，不得编造档案。
                # 例外：消息里已带身体指标/目标 → 不拦，交给 Agent 走建档（否则建档入口被堵死）。
                yield _sse(
                    "clarify",
                    {
                        "question": "首次使用需要先建一份轻量档案（性别、年龄、身高、体重、目标），"
                                    "建档后我才能按你的情况配餐。要现在建档吗？",
                        "missing_fields": _REQUIRED_PROFILE_FIELDS,
                    },
                )
                finish_reason = "clarify"
            else:
                # context 指定方案 → 先下发 current_plan（面板刷新走同结构接口）
                raw_plan_id = (req.context or {}).get("meal_plan_id")
                if raw_plan_id:
                    payload = _load_plan_payload(db, int(raw_plan_id), req.user_id)
                    if payload is None:
                        yield _sse(
                            "error",
                            {
                                "code": int(BizCode.NOT_FOUND),
                                "message": f"方案不存在或不属于当前用户: {raw_plan_id}",
                            },
                        )
                        finish_reason = "error"
                    else:
                        meal_plan_id = payload["plan_id"]
                        yield _sse("artifact", {"type": "current_plan", "payload": payload})

                if finish_reason != "error":
                    try:
                        for event, data in _agent_events(req, conversation_id, token):
                            if event == "message":
                                assistant_text.append(data.get("content") or "")
                            elif event == "artifact":
                                # Agent 生成方案后下发的卡片：把 payload.plan_id 回填到 done，
                                # 前端靠 done.meal_plan_id 跳转 / 换候选 / 固定；不回填就一直是 null
                                pid = (data.get("payload") or {}).get("plan_id")
                                if meal_plan_id is None and pid not in (None, "", 0):
                                    try:
                                        meal_plan_id = int(pid)
                                    except (TypeError, ValueError):
                                        logger.warning("Agent artifact 的 plan_id 非整数：%r", pid)
                            elif event == "error":
                                finish_reason = "error"
                            yield _sse(event, data)
                    except BizError as e:
                        finish_reason = "error"
                        yield _sse("error", {"code": int(e.code), "message": e.message})
                    except httpx.HTTPError as e:
                        # Agent 未启动 / 网络不可达：降级为兜底文本，前端可继续演示
                        logger.warning("Agent 服务不可达（%s），降级为兜底回复", type(e).__name__)
                        assistant_text.append(_PLACEHOLDER_REPLY)
                        yield _sse(
                            "message",
                            {"type": "text", "content": _PLACEHOLDER_REPLY},
                        )
        except BizError as e:
            yield _sse("error", {"code": int(e.code), "message": e.message})
            finish_reason = "error"
        except Exception as e:  # noqa: BLE001
            # 流已开始后无法改用 HTTP 状态码，只能以 error 事件收尾（契约 §2.7）
            logger.exception("对话流处理失败")
            yield _sse(
                "error",
                {
                    "code": int(BizCode.AGENT_CALL_FAILED),
                    "message": f"对话流处理失败：{type(e).__name__}",
                },
            )
            finish_reason = "error"
        finally:
            try:
                _save_message(conversation_id, "assistant", "".join(assistant_text), db)
            except Exception:  # noqa: BLE001
                logger.exception("助手回复落库失败（不影响已下发的流）")
            yield _sse(
                "done",
                {
                    "conversation_id": conversation_id,
                    "meal_plan_id": meal_plan_id,
                    "finish_reason": finish_reason,
                },
            )

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
