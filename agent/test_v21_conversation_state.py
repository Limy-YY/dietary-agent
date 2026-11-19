import unittest
from unittest.mock import patch
import agent
import conversation_state as cs
import local_edits as le
import regenerate_flow as rf

class ConversationTests(unittest.TestCase):
    def setUp(self):cs.clear_for_tests()
    def test_user_and_conversation_isolation(self):
        with cs.locked('u','A') as a:a[rf.KEY]={'meal':'午'};le.remember(a,{'meal_plan_id':1,'slots':[]})
        with cs.locked('u','B') as b:self.assertNotIn(rf.KEY,b);self.assertFalse(le.registry(b))
        with cs.locked('v','A') as other:self.assertFalse(le.registry(other))
    def test_new_plan_takes_over_only_same_conversation(self):
        with cs.locked('u','A') as a:a[rf.KEY]={'meal':'午'}
        with cs.locked('u','B') as b:b[rf.KEY]={'meal':'早'}
        with patch.object(agent,'classify',return_value={'intent':'plan_custom'}), \
             patch.object(agent,'_load_profile',return_value={'user_id':'u'}), \
             patch.object(agent,'_agent_loop',return_value={'text':'generated','blocks':[]}) as loop:
            result=agent.run('u','帮我安排11月20日至22日三餐',conversation_id='A')
        self.assertEqual(result['text'],'generated');self.assertEqual(loop.call_count,1)
        with cs.locked('u','A') as a:self.assertNotIn(rf.KEY,a)
        with cs.locked('u','B') as b:self.assertIn(rf.KEY,b)
    def test_registry_number_is_stable_and_reset_ignored(self):
        state={};p1={'meal_plan_id':1,'slots':[]};p2={'meal_plan_id':2,'slots':[]}
        le.remember(state,p1);le.remember(state,p2,reset=True);le.remember(state,{'meal_plan_id':1,'status':'fixed','slots':[]})
        self.assertEqual([(p['meal_plan_id'],p['display_index']) for p in le.registry(state)],[(1,1),(2,2)])
    def test_old_card_context_targets_exact_plan_and_slot(self):
        p1={'meal_plan_id':1,'slots':[{'meal_slot_id':101,'meal_type':'午'}]}
        p2={'meal_plan_id':2,'slots':[{'meal_slot_id':201,'meal_type':'午'}]}
        state={};le.remember(state,p1);le.remember(state,p2)
        with patch.object(agent.bc,'get_meal_plan',return_value=p1):
            chosen=agent._operation_plan(state,'换一换午餐',{'meal_plan_id':1})
        slot=agent._operation_slot(chosen,'午餐',{'meal_slot_id':101})
        self.assertEqual(chosen['meal_plan_id'],1)
        self.assertEqual(slot['meal_slot_id'],101)

if __name__=='__main__':unittest.main()

