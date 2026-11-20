"""会话列表 / 历史消息返回结构（P1 会话列表后端化）。"""
from datetime import datetime

from pydantic import BaseModel


class ConversationItem(BaseModel):
    """一条会话摘要：列表页只展示这些字段，不拉全量消息。"""

    conversation_id: int
    user_id: str
    title: str | None = None
    created_at: datetime
    updated_at: datetime
    message_count: int
    last_message: str | None = None
    last_message_at: datetime | None = None


class MessageItem(BaseModel):
    """一条消息：历史详情页用。"""

    message_id: int
    conversation_id: int
    role: str
    content: str | None = None
    created_at: datetime
    referenced_plan_id: int | None = None
    intent: str | None = None
