import asyncio
import json
import unittest

import main as agent_main
import agent as agent_module


def _parse_sse(frames):
    """把 _stream 产出的 SSE 字符串解析成 [(event, data)]。"""
    events = []
    for frame in frames:
        event = data = None
        for line in frame.strip().split("\n"):
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:].strip())
        if event is not None:
            events.append((event, data))
    return events


async def _drive(req):
    return [frame async for frame in agent_main._stream(req)]


class MainStreamTests(unittest.TestCase):
    def test_error_path_ends_with_done(self):
        """BUG-041：agent.run 抛异常时，_stream 必须仍以 done 收尾。

        直连 Agent 8001 /chat 的客户端依赖 done 结束流；若异常后只发 error
        不发 done，客户端会一直挂起。这里打桩 agent.run 抛异常，断言事件序列
        以 done(finish_reason=error) 收尾。
        """
        original_run = agent_module.run

        def boom(*args, **kwargs):
            raise RuntimeError("模拟生成失败")

        agent_module.run = boom
        try:
            req = agent_main.AgentChatRequest(user_id="u1", message="hi")
            frames = asyncio.run(_drive(req))
        finally:
            agent_module.run = original_run

        events = _parse_sse(frames)
        self.assertTrue(events, "异常路径不应产出空流")
        self.assertEqual([e for e, _ in events][-1], "done",
                         "异常后最后一帧必须是 done，否则直连客户端挂起")
        self.assertEqual(events[-1][1].get("finish_reason"), "error")


if __name__ == "__main__":
    unittest.main()
