"""Exercise the HTTP/SSE router, stubbing DB reads and upstream Agent calls."""
import json
import unittest
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.routers import chat


def frames(text):
    return [(p.splitlines()[0].removeprefix('event: '), json.loads(p.splitlines()[1].removeprefix('data: ')))
            for p in text.strip().split('\n\n') if p.startswith('event: ')]


class ChatCardContext(unittest.TestCase):
    def request(self, payload, action, stream):
        app = FastAPI(); app.include_router(chat.router)
        app.dependency_overrides[chat.get_db] = lambda: object()
        with patch.object(chat, '_get_or_create_conversation', return_value=7), \
             patch.object(chat, '_load_history', return_value=[]), \
             patch.object(chat, '_save_message'), \
             patch.object(chat, '_profile_exists', return_value=True), \
             patch.object(chat, '_load_plan_payload', return_value=payload), \
             patch.object(chat, '_agent_events', side_effect=stream) as upstream:
            resp = TestClient(app).post('/agent/chat', json={'user_id':'u', 'conversation_id':7,
                'message':'操作餐卡','silent':True,'context':{'meal_plan_id':101,'meal_slot_id':8,'action':action}})
            self.assertEqual(resp.status_code, 200)
            return frames(resp.text), upstream.call_count

    def test_all_three_actions_reach_agent_with_canonical_id(self):
        for action in ('swap_candidate', 'choose_candidate', 'confirm'):
            with self.subTest(action=action):
                events, count = self.request({'meal_plan_id':101,'slots':[]}, action,
                    lambda *args: iter([('artifact', {'type':'meal_card','payload':{'meal_plan_id':101}})]))
                self.assertEqual(count,1)
                self.assertEqual([name for name,_ in events], ['artifact','artifact','done'])
                self.assertEqual(events[-1][1]['meal_plan_id'],101)
                self.assertEqual(events[-1][1]['finish_reason'],'stop')

    def test_missing_or_foreign_plan_stops_before_agent(self):
        events,count = self.request(None,'confirm',lambda *args: iter([]))
        self.assertEqual(count,0)
        self.assertEqual(events[-1][1]['finish_reason'],'error')

    def test_unreachable_agent_not_success(self):
        def offline(*args): raise httpx.ConnectError('offline')
        events,count = self.request({'meal_plan_id':101},'confirm',offline)
        self.assertEqual(count,1)
        self.assertIn('error',[e for e,_ in events])
        self.assertEqual(events[-1][1]['finish_reason'],'error')

if __name__ == '__main__': unittest.main()
