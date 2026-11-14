"""Agent 对话（API-14）请求模型。"""
from pydantic import BaseModel


class ChatRequest(BaseModel):
    user_id: str
    message: str
    conversation_id: int | None = None
    # 契约 v1.2 §API-14：{"meal_plan_id": 101}，用于面板刷新时下发 current_plan
    context: dict | None = None
