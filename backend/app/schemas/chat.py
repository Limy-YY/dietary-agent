"""Agent 对话（API-14）请求模型。"""
from pydantic import BaseModel


class ChatRequest(BaseModel):
    # 身份以 JWT 为准（路由里 req.user_id = decode_token(token) 覆盖），请求体可不传（BUG-002）。
    user_id: str | None = None
    message: str
    conversation_id: int | None = None
    # 契约 v1.2 §API-14：{"meal_plan_id": 101}，用于面板刷新时下发 current_plan
    context: dict | None = None
    # 静默按钮动作（换一换/选用/确认）：透传给 Agent 跳过 LLM 叙事，直接落卡 + done。
    # 前端 silentAction 只消费 meal_card、正文被丢弃，不等 DeepSeek 能省下数秒延迟。
    silent: bool = False
