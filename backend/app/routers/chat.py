"""Agent 对话接口（API-14 / POST /agent/chat，SSE 流式）。

当前状态：SSE 通道 + 会话自动创建 + 消息落库已完成；Agent 服务尚未接入。
按契约 v1.2 §2.7，事件全集为 session / message / artifact / clarify / error / done，
本实现把六类事件全部接线；Agent 服务接入后只需把占位回复换成真实调用，逐事件转发即可。

Agent 未接入期间的确定性兜底：
- 档案缺失 → clarify（question + missing_fields），不伪造回答
- 请求 context 带 meal_plan_id → artifact(type=current_plan)，payload 与 API-04 出参同构
- 流内异常 → error(code=2002) 后再 done(finish_reason=error)
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

# 建档所需的轻量字段（与契约 §3.1 必填项一致），clarify 时原样下发
_REQUIRED_PROFILE_FIELDS = ["sex", "age", "height_cm", "weight_kg", "goal_code"]


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
    """current_plan 的 payload：与 API-04 出参同构，仅做归属校验与字段改名。"""
    row = db.execute(
        text(
            "SELECT meal_plan_id, user_id, plan_type, plan_date, goal_energy_kcal, "
            "macro_ratio, meals, sources, created_at "
            "FROM app.meal_plan WHERE meal_plan_id = :pid AND user_id = :uid"
        ),
        {"pid": plan_id, "uid": user_id},
    ).mappings().first()
    if row is None:
        return None
    return {
        "plan_id": row["meal_plan_id"],
        "user_id": row["user_id"],
        "plan_type": row["plan_type"],
        "plan_date": row["plan_date"].isoformat() if row["plan_date"] else None,
        "goal_energy_kcal": (
            float(row["goal_energy_kcal"]) if row["goal_energy_kcal"] is not None else None
        ),
        "macro_ratio": row["macro_ratio"],
        "meals": row["meals"],
        "sources": row["sources"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


@router.post("/chat")
def agent_chat(req: ChatRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    """与营养智能体多轮对话（SSE 流式；会话缺省自动创建）。"""
    conversation_id = _get_or_create_conversation(req, db)
    _save_message(conversation_id, "user", req.message, db)

    def _stream():
        yield _sse("session", {"conversation_id": conversation_id})
        finish_reason = "stop"
        meal_plan_id: int | None = None

        try:
            if not _profile_exists(db, req.user_id):
                # 契约 §2.7：信息不足必须 clarify 追问，不得编造档案
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
                yield _sse(
                    "message",
                    {"type": "text", "content": _PLACEHOLDER_REPLY, "conversation_id": conversation_id},
                )
                _save_message(conversation_id, "assistant", _PLACEHOLDER_REPLY, db)

                # context 指定方案 → 下发 current_plan（面板刷新走同结构接口）
                raw_plan_id = (req.context or {}).get("meal_plan_id")
                if raw_plan_id:
                    payload = _load_plan_payload(db, int(raw_plan_id), req.user_id)
                    if payload is None:
                        yield _sse(
                            "error",
                            {"code": int(BizCode.NOT_FOUND), "message": f"方案不存在或不属于当前用户: {raw_plan_id}"},
                        )
                        finish_reason = "error"
                    else:
                        meal_plan_id = payload["plan_id"]
                        yield _sse("artifact", {"type": "current_plan", "payload": payload})
        except BizError as e:
            yield _sse("error", {"code": int(e.code), "message": e.message})
            finish_reason = "error"
        except Exception as e:  # noqa: BLE001
            # 流已开始后无法改用 HTTP 状态码，只能以 error 事件收尾（契约 §2.7）
            yield _sse(
                "error",
                {"code": int(BizCode.AGENT_CALL_FAILED), "message": f"对话流处理失败：{type(e).__name__}"},
            )
            finish_reason = "error"
        finally:
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
