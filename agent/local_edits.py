"""Resolve real identities, never default to the first matching slot in a multi-plan/day context."""
from datetime import date, timedelta
import re
import target_resolver as tr


def plan_id(plan):
    return plan.get('meal_plan_id') or plan.get('plan_id')


def remember(state, plan, reset=False):
    # reset is retained for old callers but intentionally ignored: numbering is
    # stable for the lifetime of this conversation.
    plans = list(state.get('v21_plans') or [])
    if plan_id(plan) is None: raise ValueError('后端未返回真实方案 ID')
    for i, item in enumerate(plans):
        if str(plan_id(item)) == str(plan_id(plan)):
            plan['display_index']=item.get('display_index',i+1);plans[i] = plan; break
    else:
        plan['display_index']=len(plans)+1;plans.append(plan)
    state['v21_plans'] = plans
    state['current_plan'] = plan
    state['active_plan_id'] = plan_id(plan)


def registry(state):
    return state.get('v21_plans') or ([state['current_plan']] if state.get('current_plan') else [])


def resolve_plan(state,args):
    plans = registry(state)
    if not plans: raise ValueError('还没有可定位的方案，请先生成方案')
    index = args.get('plan_index')
    if index is None:
        if len(plans) != 1: raise ValueError('有多份方案，请说明是第几份方案')
        return plans[0]
    if type(index) is not int or not 1 <= index <= len(plans): raise ValueError('方案序号无效，请指定已有方案')
    return plans[index-1]


def resolve_slot(plan,args):
    slots = plan.get('slots') or []
    mt = {'早餐':'早','午餐':'午','晚餐':'晚','breakfast':'早','lunch':'午','dinner':'晚'}.get(args.get('meal_type'),args.get('meal_type'))
    day = args.get('day_index'); exact = args.get('slot_date')
    if day is not None:
        dates = sorted({s.get('slot_date') for s in slots if s.get('slot_date')})
        if type(day) is not int or not 1 <= day <= len(dates): raise ValueError('方案日期序号无效')
        if exact and exact != dates[day-1]: raise ValueError('日期与第几天不一致')
        exact = dates[day-1]
    matches = [s for s in slots if (not mt or s.get('meal_type') == mt) and (not exact or s.get('slot_date') == exact)]
    if len(matches) != 1: raise ValueError('请明确该方案中的日期（第几天）及餐次')
    return matches[0]


def resolve_dish(slot, text):
    selected = slot.get('selected_candidate') or next((c for c in slot.get('candidates',[]) if c.get('candidate_id') == slot.get('selected_candidate_id')), None)
    if not selected: raise ValueError('餐位无选中候选')
    if not text: raise ValueError('请说明要替换哪一道菜')
    dishes = [d for d in selected.get('dishes',[]) if text == d.get('name') or text == d.get('dish_id')]
    if not dishes: dishes = [d for d in selected.get('dishes',[]) if text in d.get('name','')]
    if len(dishes) != 1: raise ValueError('未能唯一定位菜式，请使用卡片中的具体菜名')
    return dishes[0]['dish_id']


def explicit_target(message, args):
    """Only trust a plan/day ordinal or date grounded in the actual user message."""
    args = dict(args)
    numbers = {"一":1,"二":2,"两":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9,"十":10}
    def number(value): return int(value) if value.isdigit() else numbers[value]
    indices = tr.plan_indices(message)
    if len(indices)>1:
        raise ValueError('请唯一指定一份方案')
    args['plan_index'] = indices[0] if indices else None
    m = re.search(r"第\s*([0-9]+|[一二两三四五六七八九十])\s*天",message)
    args['day_index'] = number(m.group(1)) if m else None
    m = re.search(r"\d{4}-\d{1,2}-\d{1,2}|\d{4}年\d{1,2}月\d{1,2}日",message)
    args['slot_date'] = m.group(0) if m else None
    if '后天' in message: args['slot_date'] = (date.today()+timedelta(days=2)).isoformat()
    elif '明天' in message: args['slot_date'] = (date.today()+timedelta(days=1)).isoformat()
    elif '今天' in message: args['slot_date'] = date.today().isoformat()
    # Month/day without year is not safe to infer across years; ask for exact date if needed.
    m = re.search(r"(早餐|早饭|早上|早晨|午餐|午饭|中午|午间|晚餐|晚饭|晚上|晚间)", message)
    if m:
        meal_map = {
            '早饭': '早餐', '早上': '早餐', '早晨': '早餐',
            '午饭': '午餐', '中午': '午餐', '午间': '午餐',
            '晚饭': '晚餐', '晚上': '晚餐', '晚间': '晚餐',
        }
        args['meal_type'] = meal_map.get(m.group(1), m.group(1))
    return args


def execute(bc,state,name,args,message):
    args = explicit_target(message,args)
    cached_plans=registry(state)
    plans=[]
    for cached in cached_plans:
        actual=bc.get_meal_plan(plan_id(cached))
        if str(plan_id(actual))!=str(plan_id(cached)):raise ValueError('后端返回的方案 ID 不一致，已停止操作')
        plans.append(actual)
    target=tr.resolve(plans,message,args)
    plan,slot=target.plan,target.slot
    if plan.get('status') != 'candidates': raise ValueError('方案已生效（已固定），不能直接修改。如需调整，请重新生成一份覆盖该餐次的方案，确认后选择「替换」取代当前方案。')
    payload = dict(meal_plan_id=plan_id(plan),meal_slot_id=slot['meal_slot_id'],expected_candidate_id=slot['selected_candidate_id'],
                   exclude_ingredients=args.get('exclude_ingredients') or [],soft_avoid=args.get('soft_avoid') or [])
    if name == 'regenerate_slot':
        payload['keep_dish_ids'] = [resolve_dish(slot,x) for x in args.get('keep_dish_names') or []]
        updated = bc.regenerate_slot(**payload)
    else:
        payload['dish_id'] = resolve_dish(slot,args.get('old_dish_name'))
        payload['replacement_query'] = args.get('replacement_query') or ''
        payload['allow_approximate'] = True
        # Do not auto-authorize nutrition relaxation.
        updated = bc.replace_dish(**payload)
    remember(state,updated)
    new_slot = next(s for s in updated['slots'] if s['meal_slot_id'] == slot['meal_slot_id'])
    selected = new_slot['selected_candidate']
    names = '、'.join(d['name'] for d in selected['dishes'])
    flags = selected.get('reason_codes') or []
    warnings = [label for key,label in [('macro_range_relaxed','营养近似结果'),('oil_salt_unknown','油盐数据不完整'),('allergen_unverified','过敏原未核查')] if key in flags]
    reply = f"已调整 {new_slot['slot_date']} {new_slot['meal_type']}餐：{names}。其他餐位不变，方案仍待确认。"
    if warnings: reply += '注意：'+'、'.join(warnings)+'。'
    return updated,reply


PROPERTIES = {'plan_index':{'type':'integer','description':'用户指定第几份方案，未指定且只有一份可省略'},
              'day_index':{'type':'integer','description':'方案中第几天'},'slot_date':{'type':'string','description':'用户明确给出的 YYYY-MM-DD'},
              'meal_type':{'type':'string','enum':['早餐','午餐','晚餐']},
              'exclude_ingredients':{'type':'array','items':{'type':'string'}},
              'soft_avoid':{'type':'array','items':{'type':'string'}}}
TOOLS = [
    {'type':'function','function':{'name':'regenerate_slot','description':"重新生成整顿餐次（早餐/午餐/晚餐）。当用户说「换早餐」「早餐换成 A + B」「某餐我想吃…」或想把单菜餐卡改成多道菜组合时，必须调用此工具。",
     'parameters':{'type':'object','properties':{**PROPERTIES,'keep_dish_names':{'type':'array','items':{'type':'string'}}}}}},
    {'type':'function','function':{'name':'replace_dish',"description": "仅用于把当前餐卡中【已存在的某一道具体菜】一对一替换成另一道菜。严禁在「把早餐/午餐/晚餐换成…」「换成 A + B 多道菜」时调用。",
     'parameters':{'type':'object','properties':{**PROPERTIES,'old_dish_name':{'type':'string', "description": "必须严格等于当前餐卡中已存在的具体菜名，未指明旧菜时禁止调用此工具"},'replacement_query':{'type':'string','description':'指定替代食材或菜名；未要求时留空'}},'required':['old_dish_name']}}},
]
