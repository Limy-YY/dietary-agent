"""Agent 对话（API-14）请求模型。"""
from pydantic import BaseModel


class ChatRequest(BaseModel):
    user_id: str
    message: str
    conversation_id: int | None = None
