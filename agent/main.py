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
import config

app = FastAPI(title="膳食搭配智能体 - Agent 服务", version="0.1.0")


class AgentChatRequest(BaseModel):
    user_id: str = "demo-user"
    message: str
    conversation_id: str | int | None = None


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _suggestions(blocks: list[dict]) -> list[str]:
    types = [b.get("type") for b in blocks]
    if "meal_card" in types:
        return ["换一换", "看完整食谱", "确认当前方案"]
    if "report" in types:
        return ["生成月膳食报告", "看看食材清单"]
    return ["生成一日三餐", "生成一周食谱", "推荐一餐搭配"]


def _stream(req: AgentChatRequest):
    conv_id = str(req.conversation_id or f"conv_{int(time.time() * 1000)}")
    yield _sse("message", {"conversation_id": conv_id, "delta": ""})

    try:
        result = agent.run(req.user_id, req.message)
    except Exception as e:  # 生成中失败 → error 事件，前端可重试
        yield _sse("error", {"code": 2003, "message": f"生成失败：{e}"})
        return

    text = result.get("text") or ""
    for i in range(0, len(text), 6):
        yield _sse("message", {"delta": text[i:i + 6]})
        # 模拟逐字流；让前端能感知到打字效果
        time.sleep(0.008)

    blocks = result.get("blocks") or []
    if blocks:
        yield _sse("message", {"meta": {"blocks": blocks}, "conversation_id": conv_id})

    yield _sse("done", {
        "conversation_id": conv_id,
        "message_id": f"msg_{int(time.time() * 1000)}",
        "finish_reason": "stop",
        "suggestions": _suggestions(blocks),
    })


@app.post("/chat")
def chat(req: AgentChatRequest) -> StreamingResponse:
    """与智能体对话（SSE）。"""
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
