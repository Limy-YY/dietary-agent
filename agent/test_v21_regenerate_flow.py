import copy, unittest
import local_edits as le
import regenerate_flow as rf

def fixture():
    plans=[]
    for pid,days,meals in [(11,3,['早','午','晚']),(12,2,['早','晚']),(13,1,['午'])]:
        slots=[]
        for day in range(days):
            for mt in meals:
                sid=pid*100+len(slots)+1
                slots.append({'meal_slot_id':sid,'slot_date':f'2026-11-{18+day:02d}','meal_type':mt,'selected_candidate_id':sid*10})
        plans.append({'meal_plan_id':pid,'status':'candidates','slots':slots})
    return plans

class Client:
    def __init__(self):
        self.plans={p['meal_plan_id']:p for p in fixture()}; self.calls=[]; self.fail_at=None
    def get_meal_plan(self,pid): return copy.deepcopy(self.plans[pid])
    def regenerate_slot(self,**args):
        self.calls.append(args)
        if len(self.calls)==self.fail_at: raise RuntimeError('模拟错误')
        p=self.plans[args['meal_plan_id']]; s=next(s for s in p['slots'] if s['meal_slot_id']==args['meal_slot_id']); assert s['selected_candidate_id']==args['expected_candidate_id']; s['selected_candidate_id']+=1
        return copy.deepcopy(p)

class Tests(unittest.TestCase):
    def setUp(self):
        self.bc=Client(); self.state={}
        for p in fixture(): le.remember(self.state,p)
    def send(self,m): return rf.handle(self.bc,self.state,m)
    def targets(self): return [(c['meal_plan_id'],c['meal_slot_id']) for c in self.bc.calls]
    def test_exact_screenshot(self):
        self.assertIn('方案1',self.send('帮我重新生成早餐。')['text']); self.assertFalse(self.bc.calls)
        self.assertIn('5 餐',self.send('全部')['text']); self.assertFalse(self.bc.calls)
        r=self.send('对，一共五餐'); self.assertIn('全部 5 餐',r['text']); self.assertEqual([p['meal_plan_id'] for p in r['updated_plans']],[11,12]); self.assertEqual(len(self.bc.calls),5)
        self.assertEqual(self.targets(),[(11,1101),(11,1104),(11,1107),(12,1201),(12,1203)])
        self.assertIsNone(self.send('确认')); self.assertEqual(len(self.bc.calls),5)
    def test_plan_aliases(self):
        for msg in ['方案1','方案①','第一份方案','第一个方案','方案一']:
            self.assertEqual(rf.plan_indices(msg),[1])
    def test_short_followup(self):
        self.send('帮我重新生成早餐'); self.assertIn('多餐',self.send('方案1')['text']); self.assertIn('3 餐',self.send('全部')['text']); self.send('确认'); self.assertEqual([c['meal_plan_id'] for c in self.bc.calls],[11]*3)
    def test_date_range(self):
        self.send('帮我重新生成早餐'); r=self.send('第一份方案，就是11.18-11.20的早餐三天重排'); self.assertIn('3 餐',r['text']); self.send('确认'); self.assertEqual(len(self.bc.calls),3)
    def test_single(self):
        self.send('重新生成第一个方案第二天的午餐，其他餐次保持不变'); self.assertEqual(self.targets(),[(11,1105)])
    def test_full_chinese_date_and_later_plan(self):
        self.assertIn('请选',self.send('帮我重新生成2026年11月18日的午餐')['text'])
        self.state.pop(rf.KEY,None);self.bc.calls.clear()
        self.send('帮我重新生成方案3中2026年11月18日的午餐')
        self.assertEqual(self.targets(),[(13,1301)])
    def test_new_plan_detection(self):
        self.assertTrue(rf.is_new_plan_request('再帮我安排11月23日的午餐'))
        self.assertFalse(rf.is_new_plan_request('重新安排方案1的午餐'))
    def test_cancel(self):
        self.send('重新生成全部早餐'); self.send('取消'); self.assertFalse(self.bc.calls); self.assertNotIn(rf.KEY,self.state)
    def test_stale(self):
        self.send('重新生成全部早餐'); self.bc.plans[12]['slots'][0]['selected_candidate_id']+=99; r=self.send('确认'); self.assertIn('未开始',r['text']); self.assertFalse(self.bc.calls)
    def test_partial_failure(self):
        self.send('重新生成全部早餐'); self.bc.fail_at=3; r=self.send('确认'); self.assertIn('2/5',r['text']); self.assertIn('未获成功确认',r['text']); self.assertEqual(len(self.bc.calls),3)
    def test_fixed(self):
        self.bc.plans[12]['status']='fixed'; self.assertIn('尚未修改',self.send('重新生成全部早餐')['text']); self.assertFalse(self.bc.calls)
    def test_new_scope(self):
        self.send('重新生成早餐'); self.send('全部'); self.send('方案①'); self.send('确认'); self.assertEqual([c['meal_plan_id'] for c in self.bc.calls],[11]*3)
    def test_complex_no_silent_drop(self):
        self.assertIsNone(self.send('重新生成方案1第二天早餐，不要牛肉')); self.assertFalse(self.bc.calls)
    def test_other_request_clears_pending(self):
        self.send('重新生成全部早餐'); self.assertIsNone(self.send('介绍一下营养知识')); self.assertIsNone(self.send('确认')); self.assertFalse(self.bc.calls)
    def test_mismatched_confirm_count(self):
        self.send("重新生成全部早餐"); self.assertIn("不是",self.send("对，一共三餐")["text"]); self.assertFalse(self.bc.calls)
    def test_narration_labels(self):
        self.assertIn('早餐3餐',rf.plan_label(fixture()[0],1)); self.assertIn('共1餐',rf.plan_label(fixture()[2],3))
if __name__=='__main__': unittest.main()
