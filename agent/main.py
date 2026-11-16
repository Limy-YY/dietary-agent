# -*- coding: utf-8 -*-
"""Agent 独立服务：FastAPI + SSE 对话。

启动：
    .\\.venv\\Scripts\\python -m uvicorn main:app --host 127.0.0.1 --port 8001

前端契约见 ../frontend/docs/agent-output-contract.md。
后端 /agent/chat 代理本服务的方式见 ../backend 的 chat.py 联调补丁（README 有说明）。
"""
from __future__ import annotations

import json
import time

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import agent
import backend_client
import config

app = FastAPI(title="膳食搭配智能体 - Agent 服务", version="0.1.0")


class AgentChatRequest(BaseModel):
    user_id: str = "demo-user"
    message: str
    conversation_id: str | int | None = None
    # 后端 /agent/chat 代调时透传调用方 JWT，Agent 再拿它去调后端 REST（否则一律 401）
    token: str | None = None


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _stream(req: AgentChatRequest):
    conv_id = str(req.conversation_id or f"conv_{int(time.time() * 1000)}")

    try:
        result = agent.run(req.user_id, req.message)
    except Exception as e:  # 生成中失败 → error 事件，前端可重试
        yield _sse("error", {"code": 2003, "message": f"生成失败：{e}"})
        return

    # 正文流式（v1.2：message 事件带 type=text/content）
    text = result.get("text") or ""
    for i in range(0, len(text), 6):
        yield _sse("message", {"type": "text", "content": text[i:i + 6]})
        time.sleep(0.008)

    # 结构化边车（v1.2：artifact 事件 type + payload，一次可多个）
    blocks = result.get("blocks") or []
    meal_plan_id = None
    for b in blocks:
        btype = b.get("type", "unknown")
        payload = {k: v for k, v in b.items() if k != "type"}
        if btype == "meal_card" and payload.get("meal_plan_id") is not None:
            meal_plan_id = payload["meal_plan_id"]
        yield _sse("artifact", {"type": btype, "payload": payload})

    yield _sse("done", {
        "conversation_id": conv_id,
        "meal_plan_id": meal_plan_id,
        "finish_reason": "stop",
    })


@app.post("/chat")
def chat(req: AgentChatRequest) -> StreamingResponse:
    """与智能体对话（SSE）。"""
    # 后端透传的 JWT 交给 backend_client，后续 REST 调用自动带 Authorization
    backend_client.set_token(req.token)
    return StreamingResponse(
        _stream(req),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/health")
def health():
    return {"code": 0, "message": "success", "data": {"status": "ok", "llm": agent.llm_available()}}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.AGENT_HOST, port=config.AGENT_PORT)
