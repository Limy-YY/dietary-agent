import asyncio
import copy
import json
import unittest
from unittest.mock import patch

import agent
import main
import conversation_state as cs
import regenerate_flow as rf


def plan(selected=11, status='candidates'):
    candidates = [{'candidate_id': i, 'dishes': [{'name': str(i)}]} for i in (11, 12)]
    return {'meal_plan_id': 1, 'status': status, 'slots': [{'meal_slot_id': 10,
            'slot_date': '2026-11-23', 'meal_type': '午', 'selected_candidate_id': selected,
            'selected_candidate': next(c for c in candidates if c['candidate_id'] == selected),
            'candidates': candidates}]}


class CardActions(unittest.TestCase):
    def setUp(self): cs.clear_for_tests()

    def run_action(self, action, updated, **extra):
        ctx = {'meal_plan_id': 1, 'meal_slot_id': 10, 'action': action, **extra}
        with cs.locked('u', 'a') as st:
            st[rf.KEY] = {'meal': '午', 'preview': []}
        with patch.object(agent.bc, 'get_meal_plan', side_effect=[plan(), updated]), \
             patch.object(agent.bc, 'swap_candidate', return_value=updated) as swap, \
             patch.object(agent.bc, 'regenerate_slot') as regen, \
             patch.object(agent.bc, 'fix_meal_plan', return_value=updated) as fix, \
             patch.object(agent, '_load_profile', return_value={}), \
             patch.object(agent, 'classify', side_effect=AssertionError('must not classify explicit action')):
            result = agent.run('u', '确认', conversation_id='a', context=ctx)
        return result, swap, regen, fix

    def test_swap_cycles_candidate(self):
        # 「换一换」= 生成期候选内瞬时轮换（IMP-059 后不再重跑引擎）。
        result, swap, regen, _ = self.run_action('swap_candidate', plan(12))
        swap.assert_called_once_with(meal_plan_id=1, meal_slot_id=10)
        regen.assert_not_called()
        self.assertEqual(result['blocks'][0]['slots'][0]['selected_candidate_id'], 12)

    def test_choose_exact_id(self):
        result, swap, _, _ = self.run_action('choose_candidate', plan(12), candidate_id=12)
        swap.assert_called_once_with(meal_plan_id=1, meal_slot_id=10, candidate_id=12)
        self.assertEqual(result['blocks'][0]['slots'][0]['selected_candidate_id'], 12)

    def test_invalid_candidate_backend_rejects(self):
        # 快速路径：候选 id 直接交给后端，后端 404 拒绝 → Agent 返回失败、不下发卡片。
        ctx = {'meal_plan_id': 1, 'meal_slot_id': 10, 'candidate_id': 99, 'action': 'choose_candidate'}
        with cs.locked('u', 'a') as st:
            st[rf.KEY] = {'meal': '午', 'preview': []}
        with patch.object(agent.bc, 'swap_candidate',
                          side_effect=agent.bc.BackendError('候选不属于该餐位', code=404)) as swap, \
             patch.object(agent, '_load_profile', return_value={}), \
             patch.object(agent, 'classify', side_effect=AssertionError('must not classify explicit action')):
            result = agent.run('u', '确认', conversation_id='a', context=ctx)
        swap.assert_called_once_with(meal_plan_id=1, meal_slot_id=10, candidate_id=99)
        self.assertFalse(result['blocks'])
        self.assertIn('选用失败', result['text'])

    def test_swap_backend_reject_not_success(self):
        # 换一换后端拒绝（无其他可选候选 / 已是当前选中）→ 不下发卡片，返回错误文案。
        # 「换一换 = 候选内瞬时轮换」后，不再用「菜品串未变」判异常——该场景由后端直接报错兜底。
        ctx = {'meal_plan_id': 1, 'meal_slot_id': 10, 'action': 'swap_candidate'}
        with cs.locked('u', 'a') as st:
            st[rf.KEY] = {'meal': '午', 'preview': []}
        with patch.object(agent.bc, 'swap_candidate',
                          side_effect=agent.bc.BackendError('该餐位没有其他可选候选', code=2006)) as swap, \
             patch.object(agent, '_load_profile', return_value={}), \
             patch.object(agent, 'classify', side_effect=AssertionError('must not classify explicit action')):
            result = agent.run('u', '确认', conversation_id='a', context=ctx)
        swap.assert_called_once_with(meal_plan_id=1, meal_slot_id=10)
        self.assertFalse(result['blocks'])
        self.assertIn('换候选失败', result['text'])

    def test_confirm_bypasses_pending(self):
        result, swap, _, fix = self.run_action('confirm', plan(status='fixed'))
        fix.assert_called_once_with(meal_plan_id=1, replace=False)
        swap.assert_not_called()
        self.assertEqual(result['blocks'][0]['status'], 'fixed')

    def events(self, result, action='confirm', **extra):
        async def collect():
            req = main.AgentChatRequest(message='确认', user_id='u', conversation_id='a', silent=True,
                context={'meal_plan_id': 1, 'meal_slot_id': 10, 'action': action, **extra})
            return [s async for s in main._stream(req)]
        with patch.object(agent, 'run', return_value=result):
            return '\n'.join(asyncio.run(collect()))

    def test_silent_text_failure(self):
        events = self.events({'text': '已有冲突', 'blocks': []})
        self.assertIn('event: error', events)
        self.assertIn('已有冲突', events)
        self.assertIn('"finish_reason": "error"', events)

    def test_silent_confirm_success(self):
        events = self.events({'blocks': [agent.blocks.meal_card_block(plan(status='fixed'))]})
        self.assertNotIn('event: error', events)
        self.assertIn('"finish_reason": "stop"', events)

    def test_silent_wrong_candidate_fails(self):
        events = self.events({'blocks': [agent.blocks.meal_card_block(plan())]}, 'choose_candidate', candidate_id=12)
        self.assertIn('event: error', events)

if __name__ == '__main__': unittest.main()
