"""会话列表与历史消息（P1：会话列表后端化）。

背景：前端原先把 conversation_id 只存在 localStorage，换设备或清缓存即丢失，
历史会话无法回看。本接口把「我的会话」和「某个会话的消息」交给后端提供。

身份约定
- 带 `Authorization: Bearer <token>` 时以 token 解出的 user_id 为准（优先于 query）；
- 无 token 时允许显式传 user_id，供前端迁移期兜底；
- 会话详情一律做归属校验，非本人 403，与他人会话返回 NOT_FOUND（不暴露是否存在）。

数据来源：app.conversation / app.message（chat.py 在 SSE 链路里已落库）。
"""
import json

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import BizCode, BizError
from app.core.response import ApiResponse, PageData, page_data
from app.core.security import decode_token
from app.db import get_db
from app.routers.chat import _extract_bearer
from app.schemas.conversations import ConversationItem, MessageItem, RenameConversationRequest

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _resolve_user_id(user_id: str | None, authorization: str | None) -> str:
    """token 优先，其次显式 user_id；都没有则 401。"""
    token = _extract_bearer(authorization)
    if token:
        try:
            return decode_token(token)
        except Exception as exc:  # noqa: BLE001 - 统一转业务错误码
            raise BizError(code=BizCode.UNAUTHORIZED, message="token 无效或已过期") from exc
    if user_id:
        return user_id
    raise BizError(code=BizCode.UNAUTHORIZED, message="缺少身份：请带 Authorization 或 user_id")


def _ensure_owner(db: Session, conversation_id: int, uid: str) -> None:
    """会话归属校验：不存在 → 1004，非本人 → 1003。"""
    owner = db.execute(
        text("SELECT user_id FROM app.conversation WHERE conversation_id = :cid"),
        {"cid": conversation_id},
    ).mappings().first()
    if owner is None:
        raise BizError(code=BizCode.NOT_FOUND, message=f"会话不存在: {conversation_id}")
    if owner["user_id"] != uid:
        raise BizError(code=BizCode.FORBIDDEN, message="会话归属校验失败")


@router.get("")
def list_conversations(
    user_id: str | None = Query(None, description="用户 ID（迁移期兜底，token 存在时忽略）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[ConversationItem]]:
    """按最近消息时间倒序返回会话列表，附消息数与最后一条助手回复摘要。"""
    uid = _resolve_user_id(user_id, authorization)

    total = db.execute(
        text("SELECT count(*) FROM app.conversation WHERE user_id = :uid"),
        {"uid": uid},
    ).scalar_one()

    offset = (page - 1) * page_size
    rows = db.execute(
        text(
            """
            SELECT c.conversation_id, c.user_id, c.title, c.created_at,
                   COALESCE(m.last_at, c.created_at) AS updated_at,
                   COALESCE(m.cnt, 0)            AS message_count,
                   m.last_content                AS last_message,
                   m.last_at                     AS last_message_at
            FROM app.conversation c
            LEFT JOIN LATERAL (
                SELECT count(*) AS cnt,
                       max(msg.created_at) AS last_at,
                       (SELECT content FROM app.message
                         WHERE conversation_id = c.conversation_id AND role = 'assistant'
                         ORDER BY message_id DESC LIMIT 1) AS last_content
                FROM app.message msg
                WHERE msg.conversation_id = c.conversation_id
            ) m ON TRUE
            WHERE c.user_id = :uid
            ORDER BY updated_at DESC, c.conversation_id DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {"uid": uid, "limit": page_size, "offset": offset},
    ).mappings().all()

    items = [ConversationItem(**{k: r[k] for k in r.keys()}) for r in rows]
    return ApiResponse(code=0, message="ok", data=page_data(items, total, page, page_size))


@router.get("/{conversation_id}/messages")
def list_messages(
    conversation_id: int,
    user_id: str | None = Query(None, description="用户 ID（迁移期兜底，token 存在时忽略）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[MessageItem]]:
    """按时间正序返回某会话的消息（分页），供历史详情页复盘。"""
    uid = _resolve_user_id(user_id, authorization)

    _ensure_owner(db, conversation_id, uid)

    total = db.execute(
        text("SELECT count(*) FROM app.message WHERE conversation_id = :cid"),
        {"cid": conversation_id},
    ).scalar_one()

    offset = (page - 1) * page_size
    rows = db.execute(
        text(
            """
            SELECT message_id, conversation_id, role, content, created_at,
                   referenced_plan_id, intent, structured_output
            FROM app.message
            WHERE conversation_id = :cid
            ORDER BY message_id
            LIMIT :limit OFFSET :offset
            """
        ),
        {"cid": conversation_id, "limit": page_size, "offset": offset},
    ).mappings().all()

    items = []
    for r in rows:
        d = dict(r)
        so = d.get("structured_output")
        if isinstance(so, str):
            try:
                so = json.loads(so)
            except json.JSONDecodeError:
                so = None
        d["structured_output"] = so if isinstance(so, dict) else None
        items.append(MessageItem(**d))
    return ApiResponse(code=0, message="ok", data=page_data(items, total, page, page_size))


@router.patch("/{conversation_id}")
def rename_conversation(
    conversation_id: int,
    payload: RenameConversationRequest,
    user_id: str | None = Query(None, description="用户 ID（迁移期兜底，token 存在时忽略）"),
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> ApiResponse[None]:
    """重命名会话（标题 1~24 字）。"""
    uid = _resolve_user_id(user_id, authorization)
    _ensure_owner(db, conversation_id, uid)
    title = (payload.title or "").strip()[:24]
    if not title:
        raise BizError(code=BizCode.PARAM_ERROR, message="标题不能为空")
    db.execute(
        text("UPDATE app.conversation SET title = :title WHERE conversation_id = :cid"),
        {"title": title, "cid": conversation_id},
    )
    db.commit()
    return ApiResponse(code=0, message="ok", data=None)


@router.delete("/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    user_id: str | None = Query(None, description="用户 ID（迁移期兜底，token 存在时忽略）"),
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> ApiResponse[None]:
    """删除会话及其消息（硬删）。"""
    uid = _resolve_user_id(user_id, authorization)
    _ensure_owner(db, conversation_id, uid)
    db.execute(text("DELETE FROM app.message WHERE conversation_id = :cid"), {"cid": conversation_id})
    db.execute(text("DELETE FROM app.conversation WHERE conversation_id = :cid"), {"cid": conversation_id})
    db.commit()
    return ApiResponse(code=0, message="ok", data=None)
