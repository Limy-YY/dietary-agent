"""Deterministic multi-turn regeneration. Never infer identity from LLM narration."""
import re
from datetime import date, timedelta
import local_edits as le
import target_resolver as tr

KEY = 'v21_pending_regen'
NUMBERS = {'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10, **{c:i for i,c in enumerate('①②③④⑤⑥⑦⑧⑨⑩',1)}}
N = r'[0-9]+|[一二两三四五六七八九十①②③④⑤⑥⑦⑧⑨⑩]'
PLAN_RE = re.compile(rf'第\s*({N})\s*(?:份|个|套)(?:方案)?|方案\s*(?:第\s*)?({N})(?:号)?')
DAY_RE = re.compile(rf'第\s*({N})\s*天')
MEALS = {'早餐':'早','早饭':'早','午餐':'午','午饭':'午','中餐':'午','晚餐':'晚','晚饭':'晚'}
REGEN = re.compile(r'重新(?:生成|安排|排|配)|重排|重做|重(?:新)?(?:生成|安排|排)')
ALL = re.compile(r'全部|所有|都(?:重排|重新|要|换)|两份都|三份都|全(?:部)?重排|每(?:一)?天')
CONFIRM = re.compile(r'^(?:对(?:的)?|是(?:的)?|嗯|好(?:的)?|确认|开始|可以|没错|就这样|执行|一共[五5]餐)(?:[，,、。！!\s]*(?:一共|共|总共)?[一二三四五六七八九十0-9]+(?:餐|顿))?[。！!\s]*$')
CANCEL = re.compile(r'^(?:取消|算了|不用了|不改了|先不改)[。！!\s]*$')


def number(value):
    return int(value) if value.isascii() and value.isdigit() else NUMBERS[value]


def plan_indices(message):
    return tr.plan_indices(message)

def is_new_plan_request(message):
    """A fresh plan request takes ownership from any unfinished edit task."""
    msg=(message or '').strip()
    asks=bool(re.search(r'安排|生成|推荐|规划|制定|配(?:一|个|份|套)',msg))
    scope=bool(re.search(r'方案|三餐|食谱|菜单|早餐|午餐|晚餐|早晚餐|一周|七天|\d+天|\d{1,2}[月./]\d{1,2}',msg))
    existing=bool(PLAN_RE.search(msg) or DAY_RE.search(msg) or re.search(r'其他.+不变|只(?:改|换|重排)|替换|换掉',msg))
    explicit_new=bool(re.search(r'新(?:的)?(?:方案|食谱|菜单)|再(?:帮我)?安排|另(?:外|一份)',msg))
    return asks and scope and (explicit_new or not existing)


def plan_label(plan, index):
    slots = plan.get('slots') or []
    dates = sorted({s['slot_date'] for s in slots})
    if not dates: return f'方案{index}（ID {le.plan_id(plan)}，无餐位）'
    counts = '、'.join(f'{label}{sum(s.get("meal_type")==mt for s in slots)}餐' for label,mt in [('早餐','早'),('午餐','午'),('晚餐','晚')] if any(s.get('meal_type')==mt for s in slots))
    return f'方案{index}（{dates[0]} 至 {dates[-1]}，{counts}，共{len(slots)}餐）'


def reply(text, plans=()):
    return {'text':text, 'updated_plans':list(plans)}


def scope_dates(msg, slots):
    return tr.scope_dates(msg,slots)


def _load(bc, state):
    plans=[]
    for cached in list(le.registry(state)):
        pid=le.plan_id(cached)
        actual=bc.get_meal_plan(pid)
        if str(le.plan_id(actual))!=str(pid): raise ValueError('后端返回的方案 ID 不一致，已停止操作')
        plans.append(actual)
    return plans


def _targets(plans, pending):
    choices = pending.get('indices')
    matching=[]
    for i,p in enumerate(plans,1):
        if choices is not None and i not in choices: continue
        slots=p.get('slots') or []
        dates=scope_dates(pending.get('date_text',''),slots)
        for s in slots:
            if s.get('meal_type')!=pending['meal']: continue
            if dates is not None and s.get('slot_date') not in dates: continue
            matching.append(dict(index=i,meal_plan_id=le.plan_id(p),meal_slot_id=s['meal_slot_id'],slot_date=s['slot_date'],meal_type=s['meal_type'],expected_candidate_id=s['selected_candidate_id'],status=p.get('status')))
    return matching


def _target_text(targets):
    grouped={}
    for t in targets: grouped.setdefault(t['index'],[]).append(t['slot_date'])
    label={'早':'早餐','午':'午餐','晚':'晚餐'}[targets[0]['meal_type']]
    return '；'.join(f'方案{i}：'+ '、'.join(sorted(ds))+f'（{label}{len(ds)}餐）' for i,ds in grouped.items())


def _apply(bc,state,targets,plans):
    # Preflight the entire frozen selection before any write. Each HTTP call commits separately.
    live={str(le.plan_id(p)):p for p in plans}
    for t in targets:
        p=live.get(str(t['meal_plan_id']))
        s=next((s for s in (p or {}).get('slots',[]) if s['meal_slot_id']==t['meal_slot_id']),None)
        if not p or p.get('status')!='candidates' or not s or s.get('selected_candidate_id')!=t['expected_candidate_id'] or s.get('slot_date')!=t['slot_date'] or s.get('meal_type')!=t['meal_type']:
            state.pop(KEY,None)
            return reply('有目标餐位已改变、被固定或不可访问，本次未开始修改。请重新指定目标。')
    updated={}; completed=[]; uncertain=None
    state.pop(KEY,None)  # never replay a confirmed write on the next message
    for t in targets:
        try:
            p=bc.regenerate_slot(**{k:t[k] for k in ('meal_plan_id','meal_slot_id','expected_candidate_id')})
            if str(le.plan_id(p))!=str(t['meal_plan_id']): raise ValueError('返回方案 ID 不匹配')
            s=next((s for s in p.get('slots',[]) if s['meal_slot_id']==t['meal_slot_id']),None)
            if not s or s.get('selected_candidate_id') in (None,t['expected_candidate_id']): raise ValueError('新候选尚未确认')
            le.remember(state,p)
            updated[str(le.plan_id(p))]=p; completed.append(t)
        except Exception as exc:
            uncertain=(t,str(exc)); break
    if uncertain:
        t,err=uncertain
        return reply(f'已确认成功重排 {len(completed)}/{len(targets)} 餐。'+('成功：'+_target_text(completed)+'。' if completed else '')+f'方案{t["index"]} {t["slot_date"]} 餐位未获成功确认：{err}。已停止，后续 {len(targets)-len(completed)-1} 餐未执行；请刷新核对失败餐位，已成功的餐不会自动回滚。',updated.values())
    return reply(f'已重新生成全部 {len(completed)} 餐：{_target_text(completed)}。其他餐位保持不变，方案仍待确认。',updated.values())


def handle(bc,state,message):
    msg=message.strip()
    old=state.get(KEY)
    meal_hits=list(dict.fromkeys(v for k,v in MEALS.items() if k in msg))
    meal=meal_hits[0] if len(meal_hits)==1 else None
    new=bool(REGEN.search(msg) and meal)
    # This narrowly fixes meal regeneration; do not silently drop richer constraints.
    complex_request=bool(re.search(r'不要|不吃|忌口|清淡|少油|保留.{1,}|换成|只换|替换|排除',msg))
    if complex_request and new:
        state.pop(KEY,None)
        return None
    indices=plan_indices(msg)
    all_scope=bool(ALL.search(msg))
    dated=bool(DAY_RE.search(msg) or re.search(r'\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[月./]\d{1,2}|今天|明天',msg))
    confirmed=bool(CONFIRM.fullmatch(msg))
    if old and CANCEL.fullmatch(msg):
        state.pop(KEY,None); return reply('已取消本次重排，没有修改方案。')
    if not new and not old: return None
    if re.search(r'不要(?:重新|重排)|不用(?:重新|重排)|别(?:重新|重排)|不需要(?:重新|重排)',msg):
        state.pop(KEY,None); return reply('已取消本次重排，没有修改方案。')
    if not new and not (indices or all_scope or dated or confirmed or (meal and len(msg)<=5)):
        # A different request invalidates the old pending action.
        state.pop(KEY,None); return None
    if old and not new and confirmed and old.get('preview'):
        count=re.search(r'(?:一共|共|总共)\s*([0-9]+|[一二三四五六七八九十])(?:餐|顿)',msg)
        if count and number(count.group(1))!=len(old['preview']):
            return reply(f'待重排范围是 {len(old["preview"])} 餐，不是你刚刚说的数量。请重新指定范围，或确认待重排的餐数。')
        try: plans=_load(bc,state)
        except Exception as exc: return reply(f'方案读取失败，未开始修改：{exc}')
        return _apply(bc,state,old['preview'],plans)
    pending=dict(old or {}) if not new else {'meal':meal}
    pending.pop('preview',None)
    if meal: pending['meal']=meal
    try: plans=_load(bc,state)
    except Exception as exc: return reply(f'方案读取失败，未开始修改：{exc}')
    if not plans: return reply('当前没有可定位的方案，请先生成方案。')
    if indices:
        if any(i<1 or i>len(plans) for i in indices): return reply('方案编号无效。'+ '；'.join(plan_label(p,i) for i,p in enumerate(plans,1)))
        pending['indices']=indices
    elif all_scope and not pending.get('indices'):
        pending['indices']=list(range(1,len(plans)+1))
    if dated: pending['date_text']=msg
    if all_scope: pending['all_days']=True
    state[KEY]=pending
    try: targets=_targets(plans,pending)
    except ValueError as exc: return reply(str(exc))
    # Ambiguous plan choice must be explicit, except when only one plan contains the requested meal.
    options=sorted({t['index'] for t in targets})
    if len(options)>1 and not pending.get('indices'):
        return reply('请选要重排的方案，回复“方案1”“方案2”等，或“全部”。\n'+'\n'.join(plan_label(p,i) for i,p in enumerate(plans,1) if i in options))
    if not targets:
        if dated or indices:state.pop(KEY,None)
        return reply('选定范围内没有该餐次或日期。请重新指定方案或日期。\n'+'\n'.join(plan_label(p,i) for i,p in enumerate(plans,1)))
    if any(t['status']!='candidates' for t in targets):
        return reply('目标包含已固定或不可修改的方案，尚未修改任何餐位。请指定待确认方案。')
    if len(targets)>1 and not (pending.get('all_days') or pending.get('date_text')):
        return reply('该范围有多餐，请回复具体日期、第几天，或“全部”。\n'+_target_text(targets))
    pending['preview']=targets
    # Single explicit target can execute immediately; batch always requires confirmation.
    if len(targets)==1 and (new or indices or dated) and not all_scope:
        return _apply(bc,state,targets,plans)
    return reply(f'将重新生成 {len(targets)} 餐：{_target_text(targets)}。其他餐位保持不变。回复“确认”或“对，一共{len(targets)}餐”执行，回复“取消”不修改。')
