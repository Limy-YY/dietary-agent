# -*- coding: utf-8 -*-
"""Agent 独立服务：FastAPI + SSE 对话。

启动：
    .\\.venv\\Scripts\\python -m uvicorn main:app --host 127.0.0.1 --port 8001

前端契约见 ../frontend/docs/agent-output-contract.md。
后端 /agent/chat 代理本服务的方式见 ../backend 的 chat.py 联调补丁（README 有说明）。
"""
from __future__ import annotations

import asyncio
import json
import time

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

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


def _suggestions(blocks: list[dict]) -> list[str]:
    types = [b.get("type") for b in blocks]
    if "meal_card" in types:
        return ["换一换", "看完整食谱", "确认当前方案"]
    if "report" in types:
        return ["生成月膳食报告", "看看食材清单"]
    return ["生成一日三餐", "生成一周食谱", "推荐一餐搭配"]


async def _stream(req: AgentChatRequest):
    conv_id = str(req.conversation_id or f"conv_{int(time.time() * 1000)}")
    yield _sse("message", {"conversation_id": conv_id, "delta": ""})

    # agent.run 是同步阻塞（内部走 requests 调后端 REST）。放到线程池执行，
    # 当前 ASGI task 的 ContextVar（token）会被复制到线程，agent 内的 REST 调用
    # 因此带上本请求的身份；并发请求各自独立 task，不串号。
    try:
        result = await run_in_threadpool(agent.run, req.user_id, req.message)
    except Exception as e:  # 生成中失败 → error 事件，前端可重试
        yield _sse("error", {"code": 2003, "message": f"生成失败：{e}"})
        return

    text = result.get("text") or ""
    for i in range(0, len(text), 6):
        yield _sse("message", {"delta": text[i:i + 6]})
        # 模拟逐字流；让前端能感知到打字效果（async 里不能阻塞 event loop）
        await asyncio.sleep(0.008)

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
async def chat(req: AgentChatRequest) -> StreamingResponse:
    """与智能体对话（SSE）。"""
    # 后端透传的 JWT 交给 backend_client，后续 REST 调用自动带 Authorization。
    # set_token 必须在 async 路由内（当前 task context）调用：ContextVar 会随该 task
    # 传播到 run_in_threadpool 的线程；若放在同步生成器里会丢失 context 而串号。
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
