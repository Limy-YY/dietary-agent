import unittest
from datetime import date
import target_resolver as tr

def plan(pid,start,days=3,meals=('早','午','晚')):
    from datetime import timedelta
    slots=[];d=date.fromisoformat(start)
    for n in range(days):
        for mt in meals:slots.append({'meal_slot_id':pid*100+len(slots),'slot_date':(d+timedelta(days=n)).isoformat(),'meal_type':mt})
    return {'meal_plan_id':pid,'status':'candidates','slots':slots}

class ResolverTests(unittest.TestCase):
    def setUp(self):self.plans=[plan(11,'2026-11-20'),plan(12,'2026-11-23',1,('午',))]
    def test_formats(self):
        for text in ('方案2 2026-11-23午餐','方案2 2026年11月23日午餐','方案2 11月23日午餐','方案2 11.23午餐'):
            with self.subTest(text=text):self.assertEqual(tr.resolve(self.plans,text).slot['meal_slot_id'],1200)
        self.assertEqual(tr.resolve(self.plans,'方案1第二天晚餐').slot['slot_date'],'2026-11-21')
    def test_searches_past_first_nonmatch(self):
        self.assertEqual(tr.resolve(self.plans,'2026年11月23日午餐').plan_index,2)
    def test_relative_and_errors(self):
        self.assertEqual(tr.scope_dates('后天',self.plans[0]['slots'],date(2026,11,18)),['2026-11-20'])
        with self.assertRaisesRegex(tr.ResolveError,'只有2份'):tr.resolve(self.plans,'方案99午餐')
        with self.assertRaisesRegex(tr.ResolveError,'多份方案'):tr.resolve([plan(1,'2026-11-20'),plan(2,'2026-11-20')],'11月21日午餐')
    def test_generation_scope(self):
        self.assertEqual(tr.generation_scope('安排11月20日至22日三餐',date(2026,11,19)),('2026-11-20','2026-11-22'))
        self.assertEqual(tr.generation_scope('安排11.20-11.22三餐',date(2026,11,19)),('2026-11-20','2026-11-22'))

if __name__=='__main__':unittest.main()

