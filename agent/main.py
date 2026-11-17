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
import threading
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
    # 最近若干轮 user/assistant 历史（后端已落库，代调时透传），供 LLM 多轮上下文
    history: list[dict] | None = None
    # 静默按钮动作（换一换/选用/确认）：跳过 LLM 叙事，直接下发结构化 block + done。
    # 前端 silentAction 只消费 meal_card、正文被丢弃，叙事纯属浪费 DeepSeek 数秒延迟。
    silent: bool = False


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _stream(req: AgentChatRequest):
    conv_id = str(req.conversation_id or f"conv_{int(time.time() * 1000)}")
    loop = asyncio.get_running_loop()
    status_q: asyncio.Queue[str] = asyncio.Queue()

    def on_status(stage: str) -> None:
        loop.call_soon_threadsafe(status_q.put_nowait, stage)

    yield _sse("message", {"conversation_id": conv_id, "delta": ""})

    # agent.run 是同步阻塞（内部走 requests 调后端 REST）。放到线程池执行，
    # 当前 ASGI task 的 ContextVar（token）会被复制到线程，agent 内的 REST 调用
    # 因此带上本请求的身份；并发请求各自独立 task，不串号。
    agent_task = asyncio.create_task(
        run_in_threadpool(agent.run, req.user_id, req.message, req.history, on_status)
    )

    # 实时转发「过程状态」（thinking 步骤），直到 agent.run 结束
    while not agent_task.done():
        try:
            stage = status_q.get_nowait()
        except asyncio.QueueEmpty:
            await asyncio.sleep(0.05)
            continue
        yield _sse("status", {"stage": stage})
    # 让事件循环先处理 run() 结束前最后一刻 call_soon_threadsafe 排队的 status，再排空
    await asyncio.sleep(0)
    while not status_q.empty():
        stage = status_q.get_nowait()
        yield _sse("status", {"stage": stage})

    try:
        result = agent_task.result()
    except Exception as e:  # 生成中失败 → error 事件，前端可重试
        yield _sse("error", {"code": 2003, "message": f"生成失败：{e}"})
        return

    # 正文先行：narration 走真 token 流（LLM stream=True），否则整段下发固定文本。
    # 先说话、再落卡，避免「静默蹦卡」的突兀感（对齐主流客户端：文字先导，产物随后淡入）。
    # silent：静默按钮动作直接跳过叙事（前端已丢弃正文），落卡 + done 即可。
    narration = result.get("narration")
    if narration is not None and not req.silent:
        # 工具已跑完，进入「组织回复」阶段：覆盖最后一条工具状态，填补 LLM 首 token 前的空档
        yield _sse("status", {"stage": "正在整理回复"})
        token_q: asyncio.Queue[str | None] = asyncio.Queue()

        def _run_stream() -> None:
            try:
                for tok in agent.stream_reply(narration):
                    loop.call_soon_threadsafe(token_q.put_nowait, tok)
            finally:
                loop.call_soon_threadsafe(token_q.put_nowait, None)

        threading.Thread(target=_run_stream, daemon=True).start()
        while True:
            tok = await token_q.get()
            if tok is None:
                break
            yield _sse("message", {"delta": tok})

        suffix = result.get("suffix")
        if suffix:
            yield _sse("message", {"delta": suffix})
    elif narration is None and not req.silent:
        text = result.get("text") or ""
        if text:
            yield _sse("message", {"delta": text})

    # 结构化 block 随后落（后端 chat.py 归一成 artifact；前端卡片淡入）
    blocks = result.get("blocks") or []
    if blocks:
        yield _sse("message", {"meta": {"blocks": blocks}, "conversation_id": conv_id})

    yield _sse("done", {
        "conversation_id": conv_id,
        "message_id": f"msg_{int(time.time() * 1000)}",
        "finish_reason": "stop",
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
