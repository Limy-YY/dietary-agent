"""Agent 对话接口（API-14 / POST /agent/chat，SSE 流式）。

当前状态：SSE 通道 + 会话自动创建 + 消息落库已完成；Agent 服务尚未接入，
流内返回占位事件。Agent 服务地址/协议与 Agent 岗联调确认后，替换
_AGENT_REPLY 为真实调用（调用 Agent 服务 → 逐事件转发到 SSE 流）。
"""
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import BizCode, BizError
from app.db import get_db
from app.schemas.chat import ChatRequest

router = APIRouter(prefix="/agent", tags=["agent"])

# 占位回复：Agent 服务接入前使用（联调项：Agent 服务地址与协议）
_PLACEHOLDER_REPLY = (
    "后端通道已连通（会话已创建，消息已记录）。Agent 服务接入后，"
    "本回复将替换为智能体的真实流式回答。"
)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


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
    db.execute(
        text(
            "INSERT INTO app.message (conversation_id, role, content, tool_calls) "
            "VALUES (:cid, :role, :content, '[]'::jsonb)"
        ),
        {"cid": conversation_id, "role": role, "content": content},
    )
    db.commit()


@router.post("/chat")
def agent_chat(req: ChatRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    """与营养智能体多轮对话（SSE 流式；会话缺省自动创建）。"""
    conversation_id = _get_or_create_conversation(req, db)
    _save_message(conversation_id, "user", req.message, db)

    def _stream():
        yield _sse("session", {"conversation_id": conversation_id})
        # Agent 服务接入点：替换为真实 Agent 调用，逐 token 转发
        yield _sse("message", {"content": _PLACEHOLDER_REPLY, "conversation_id": conversation_id})
        _save_message(conversation_id, "assistant", _PLACEHOLDER_REPLY, db)
        yield _sse("done", {"conversation_id": conversation_id})

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
