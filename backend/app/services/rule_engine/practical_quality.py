"""Culinary heuristics: practical portions and soft diversity, not medical rules."""
from collections import Counter
from math import sqrt

from .models import _UNSET

# Explicit ingredient families, not dish names; unmatched facts are not invented.
PROTEINS = {
    '鸡肉': ('鸡胸','鸡腿','鸡翅','鸡肉','鸡丁','鸡脯'),
    '猪肉': ('猪','排骨','五花肉','里脊'), '牛肉': ('牛肉','牛腩','牛里脊'),
    '羊肉': ('羊肉','羊排'), '鸭肉': ('鸭肉','鸭腿','鸭胸'),
    '鱼': ('鱼',), '水产': ('虾','蛤蜊','贝','蟹','鱿鱼','牡蛎'),
    '蛋': ('鸡蛋','鸭蛋','鹌鹑蛋'), '豆制品': ('豆腐','豆干','豆浆','鹰嘴豆','大豆','黄豆','豆皮'),
}
GRAIN = ('大米','小米','糙米','燕麦片','面粉','面条','米粉','荞麦','高粱','玉米面')
STARCHY = ('土豆','红薯','山药','玉米','南瓜')
VEG = ('白菜','菜薹','菜心','生菜','菠菜','苋菜','茼蒿','空心菜','油菜','西兰花','菜花','花椰菜','黄瓜','番茄','胡萝卜','白萝卜','芹菜','茄子','丝瓜','西葫芦','四季豆','苦瓜','甜椒','青椒','洋葱','韭菜','豆芽','蘑菇','香菇','金针菇','海带')
NUTS = ('花生','核桃','杏仁','腰果','芝麻')
DAIRY = ('牛奶','酸奶','奶酪')
FRUIT = ('苹果','香蕉','橙子','梨','葡萄','西瓜','桃','猕猴桃')
CONDIMENT = {'盐','精盐','食盐','油','橄榄油','食用油','花生油','菜籽油','酱油','生抽','老抽','醋','姜','大蒜','大葱','小葱','胡椒','糖','白糖','料酒','饮用水','水','味精','鸡精'}

def weights(d):
    from .portion_policy import ingredient_weights
    return ingredient_weights(d)

def family(n):
    return next((k for k,words in PROTEINS.items() if any(w in n for w in words)),None)

def portion_limits(d, target):
    """Grams of recipe ingredients, not finished meal weight. Broad culinary guardrails.
    Scale with target in a narrow range; never silently increase indefinitely.
    Do not interpret an ambiguous cooked/uncooked ingredient as dry weight.
    """
    w=weights(d)
    if not w:return []
    from .meal_templates import profile
    meta=profile(d); early=target.meal_type=='早'
    scale=max(.85,min(1.20,sqrt(max(float(target.kcal),1)/(600 if early else 850))))
    caps=[]
    def add(kind, grams, soft, ceiling):
        if grams>0:caps.append((kind,grams,soft*scale,ceiling*scale))
    if '主食' in meta.roles:
        # Only recipe ingredient identifiers corresponding to uncooked grains/noodles.
        raw=sum(g for n,g in w.items() if n in GRAIN)
        add('grain',raw,55 if early else 85,80 if early else 120)
        baked=sum(g for n,g in w.items() if n in ('馒头','面包'))
        add('bread',baked,100 if early else 150,150 if early else 225)
    vg=sum(g for n,g in w.items() if any(k in n for k in VEG) and n not in CONDIMENT)
    add('vegetables',vg,170 if early else 240,265 if early else 360)
    meat=sum(g for n,g in w.items() if family(n) in {'鸡肉','猪肉','牛肉','羊肉','鸭肉','鱼','水产'})
    add('meat',meat,100 if early else 150,160 if early else 220)
    return caps

def meal_options(d,target,requested=1.,limits=None):
    from .portion_policy import serving_options
    opts=serving_options(d,requested)
    limits=portion_limits(d,target) if limits is None else limits
    if not limits:return opts
    ok=lambda v:all(g*v<=cap+.01 for _,g,_,cap in limits)
    out=[v for v in opts if ok(v)]
    return tuple(sorted(out))

def portion_size_cost(combo, amounts, target, limits=None):
    if target is None:return 0.
    # Penalize large individual portions and excessive vegetables across one meal;
    # modest deviation is allowed, and energy remains part of the existing score.
    cost=0.; veg=0.
    if limits is None:limits=[portion_limits(d,target) for d in combo]
    for rows,v in zip(limits,amounts):
        for k,g,soft,cap in rows:
            actual=g*v
            cost+=.20*(max(0.,actual-soft)/max(cap-soft,1.))**2
            if k=='vegetables':veg+=actual
    threshold=260 if target.meal_type=='早' else 420
    cost+=.20*(max(0.,veg-threshold)/max(threshold*.5,1.))**2
    return cost

def dietary_attributes(combo, amounts):
    """Actual recipe-input contributions used for soft structure evaluation."""
    out={'full_staples':0,'starch_g':0.,'vegetable_g':0.,'nut_g':0.,
         'dairy_g':0.,'fruit_g':0.,'protein_g':0.}
    for d,v in zip(combo,amounts):
        w=weights(d)
        grain=sum(g for n,g in w.items() if n in GRAIN or n in ('馒头','面包','糙米饭','米饭'))*v
        starchy=sum(g for n,g in w.items() if any(x in n for x in STARCHY))*v
        veg=sum(g for n,g in w.items() if any(x in n for x in VEG)
                and not any(x in n for x in STARCHY) and n not in CONDIMENT)*v
        out['starch_g']+=grain+starchy
        out['vegetable_g']+=veg
        out['nut_g']+=sum(g for n,g in w.items() if any(x in n for x in NUTS))*v
        out['dairy_g']+=sum(g for n,g in w.items() if any(x in n for x in DAIRY))*v
        out['fruit_g']+=sum(g for n,g in w.items() if any(x in n for x in FRUIT))*v
        if getattr(d,'protein_g',None) is not None:out['protein_g']+=float(d.protein_g)*v
        from .meal_templates import profile
        if '主食' in profile(d).roles:
            dry=sum(g for n,g in w.items() if n in GRAIN)*v
            cooked=sum(g for n,g in w.items() if n in ('馒头','面包','糙米饭','米饭'))*v
            if dry>=35 or cooked>=65 or starchy>=120:out['full_staples']+=1
    return {k:(round(v,1) if isinstance(v,float) else v) for k,v in out.items()}

def composition_cost(combo, amounts, meal_type):
    """Soft cost from actual ingredient amounts; no fixed plate template."""
    a=dietary_attributes(combo,amounts);cost=0.
    cost+=.34*max(0,a['full_staples']-1)
    if meal_type in ('午','晚'):
        if a['vegetable_g']<60:cost+=.18
        elif a['vegetable_g']<120:cost+=.08
        if a['protein_g']<15:cost+=.12
        cost += .18*max(0.,a['nut_g']-20)/20
    if a['dairy_g']>=350:cost+=.18
    return cost,a

def structure_tier(attributes, meal_type):
    """Prefer an ordinary complete meal, not a mandatory three-item template.
    Unknown fixtures keep legacy ranking; side starch in a non-staple is not a
    second full staple. A substantial composite dish can supply vegetables.
    """
    if not attributes: return 0
    if meal_type in ('午','晚'):
        return (2 if attributes['full_staples']>1 or attributes['vegetable_g']<45
                else 1 if attributes['vegetable_g']<95 else 0)
    return 1 if attributes['full_staples']>1 else 0


def candidate_priority(c):
    a=getattr(c,'score_breakdown',{}).get('attributes',{})
    mt=getattr(c,'score_breakdown',{}).get('meal_type')
    tier=structure_tier(a,mt)
    # A grossly off-target meal is last resort, never preferred for appearance.
    delta=getattr(c,'score_breakdown',{}).get('energy_gap',0.)
    return (delta>.25,tier,'macro_range_relaxed' in c.reason_codes,c.score)


def main_family(c):
    # Match ingredient records and weight by actual grams; soup with a small
    # piece of meat shouldn't override a substantial main. Exclude incidental eggs.
    cached = getattr(c, '_main_family', _UNSET)
    if cached is not _UNSET:
        return cached
    from .meal_templates import profile
    totals=Counter()
    for p in getattr(c,'portions',()):
        d=p.facts; roles=profile(d).roles
        if '蛋白质菜' not in roles:continue
        factor=.65 if '汤羹' in roles else 1.
        for n,g in weights(d).items():
            f=family(n)
            if f and n not in CONDIMENT and g*p.servings>=15:
                # Soy drink is not equivalent to an equal weight of meat/solid tofu.
                totals[f]+=g*p.servings*factor*(.25 if n=='豆浆' else .75 if f=='豆制品' else 1.)
    result = totals.most_common(1)[0][0] if totals else None
    try:
        c._main_family = result
    except AttributeError:
        pass
    return result

def purchases(c):
    cached = getattr(c, '_purchases', _UNSET)
    if cached is not _UNSET:
        return cached
    from .portion_policy import main_ingredient_weights
    result = frozenset(n for p in getattr(c,'portions',()) for n,g in main_ingredient_weights(p.facts).items()
                       if g*p.servings>=15)
    try:
        c._purchases = result
    except AttributeError:
        pass
    return result

def protein_rotation(c,previous,*,families=None):
    f=main_family(c)
    if not f:return 0.
    if families is None:
        history=[v for x in previous if (v:=main_family(x))]
    else:
        history=[v for v in families if v]
    if not history:return 0.
    # Only recent meals; soft penalty, no quotas or exclusion.
    recent=history[-6:]
    return .24*(recent[-1]==f)+.12*sum(v==f for v in recent)+.07*sum(v==f for v in history)+.18*(len(recent)>=2 and recent[-2:]==[f,f])

def purchase_credit(c,previous,*,recent_purchases=None):
    if not previous:return 0.
    now=purchases(c)
    if not now:return 0.
    recent = recent_purchases if recent_purchases is not None else set().union(*(purchases(x) for x in previous[-4:]))
    # Small positive preference; do not penalize trying fresh ingredients.
    return .09*min(1.,len(now&recent)/3.)

def energy_cost(totals,target):
    actual=totals.get('kcal')
    if actual is None:return 0.
    delta=(float(actual)-target.kcal)/max(target.kcal,1.)
    return .65*abs(delta)+.35*max(0.,-delta)

def alternative_overlap(a,b):
    from .meal_templates import base_dish_id
    aa={base_dish_id(d) for d in a.dish_ids};bb={base_dish_id(d) for d in b.dish_ids}
    same=len(aa&bb)/max(len(aa|bb),1)
    f=main_family(a);g=main_family(b)
    from .meal_templates import staple_key
    ai,bi=purchases(a),purchases(b)
    ingredient_overlap=len(ai&bi)/max(len(ai|bi),1)
    sa,sb=staple_key(a),staple_key(b)
    return .44*same+.27*bool(f and f==g)+.025*bool(sa and sa==sb)+.12*ingredient_overlap


#: IMP-059 第 3 步：备选候选与「近窗已出菜」重合的惩罚权重（配合 diverse_choices 用）。
_W_WINDOW_OVERLAP = 0.6


def window_overlap(c, recent_used):
    """候选与「近窗已出菜」的重合度（0~1，非主食菜按 base_dish_id 计，主食不计）。"""
    if not recent_used:
        return 0.0
    from .meal_templates import non_staple_base_ids
    ids = non_staple_base_ids(c)
    if not ids:
        return 0.0
    return len(ids & recent_used) / len(ids)


def diverse_choices(candidates,count,recent_used=None):
    if not candidates:return []
    want=max(1,min(int(count),3));picked=[candidates[0]]
    from .meal_templates import base_dish_id
    key=lambda c:tuple(sorted(base_dish_id(d) for d in c.dish_ids))
    seen={key(picked[0])}
    remaining=list(candidates[1:])
    while len(picked)<want:
        available=[(i,c) for i,c in enumerate(remaining) if key(c) not in seen]
        if not available:break
        band=min(candidate_priority(c)[:2] for _,c in available)
        choices=[(i,c) for i,c in available if candidate_priority(c)[:2]==band]
        strict=[(i,c) for i,c in choices if 'macro_range_relaxed' not in c.reason_codes]
        choices=strict or choices
        # Preserve the contextual order as a tie-breaker and limit score sacrifice.
        best=min(c.score for _,c in choices)
        near=[(i,c) for i,c in choices if c.score<=best+.52]
        i,c=min(near,key=lambda ic:(ic[1].score+max(alternative_overlap(ic[1],x) for x in picked)
                                     +_W_WINDOW_OVERLAP*window_overlap(ic[1],recent_used)
                                     +.08*ic[0]/max(len(remaining),1),ic[0]))
        picked.append(c);seen.add(key(c));remaining.pop(i)
    return picked

def nutrition_report(c,target):
    from .models import DEFAULT_MACRO_TOLERANCE
    fields={}
    sodium=c.totals.get('sodium_mg')
    total_salt_equivalent=c.totals.get('total_salt_equivalent_g')
    if total_salt_equivalent is None and sodium is not None:
        total_salt_equivalent=round(sodium*2.54/1000,3)
    specs=[('kcal',target.kcal,target.kcal*(1-DEFAULT_MACRO_TOLERANCE),target.kcal*(1+DEFAULT_MACRO_TOLERANCE))]
    specs.extend((k,r.target,r.low,r.high) for k,r in [('protein_g',target.protein),('fat_g',target.fat),('carb_g',target.carb)])
    specs.extend([('oil_g',None,None,target.oil_limit_g),('salt_g',None,None,target.salt_limit_g),
                  ('total_salt_equivalent_g',None,None,target.salt_limit_g)])
    for k,want,lo,hi in specs:
        actual=total_salt_equivalent if k=='total_salt_equivalent_g' else c.totals.get(k)
        status='unknown' if actual is None else 'below' if lo is not None and actual<lo-.01 else 'above' if hi is not None and actual>hi+.01 else 'within_range'
        fields[k]={'target':None if want is None else round(want,2),'actual':actual,'min':None if lo is None else round(lo,2),'max':round(hi,2),'delta':None if want is None or actual is None else round(actual-want,2),'status':status,'direction':None if want is None or actual is None else ('below_target' if actual < want-.01 else 'above_target' if actual > want+.01 else 'at_target')}
    labels={'kcal':'能量','protein_g':'蛋白质','fat_g':'脂肪','carb_g':'碳水','oil_g':'添加油',
            'salt_g':'添加盐','total_salt_equivalent_g':'总钠折算盐'}
    messages=[labels[k]+{'below':'低于区间','above':'超过区间','unknown':'数据缺失'}[v['status']] for k,v in fields.items() if v['status']!='within_range']
    return {'summary_zh':'；'.join(messages) if messages else '已知宏量、添加油盐及总钠折算盐在设定区间内；不代表所有营养达标',
            'fields':fields,'sodium_mg':sodium,
            'total_salt_equivalent_g':total_salt_equivalent,
            'salt_limit_basis':'total_sodium_salt_equivalent; added salt reported separately and not added twice',
            'score':getattr(c,'score',None),'score_breakdown':getattr(c,'score_breakdown',{}),
            'approximate':'macro_range_relaxed' in c.reason_codes,
            'unknown_micro':[k for k,v in (getattr(c,'micro_estimate',{}) or {}).items() if v is None],
            'relaxation_notes':[n for n in (getattr(c,'notes',[]) or []) if '近似' in n or '放宽' in n or '缺失' in n]}


def plan_quality_diagnostics(slots):
    rows=[];previous=[];days={}
    from .quality import selected
    families=Counter(); reused=0; total=0
    for s in slots:
        c=selected(s)
        if c is None:continue
        f=main_family(c)
        if f and s.meal_type in ('午','晚'):families[f]+=1
        now=purchases(c); reused+=len(now&set().union(*(purchases(p) for p in previous[-4:]))); total+=len(now)
        rows.append({'date':str(s.slot_date),'meal_type':s.meal_type,'main_protein':f,'ingredients':sorted(now),'selected':nutrition_report(c,s.target),'alternatives':[{'candidate_id':p.candidate_id,'main_protein':main_family(p),'overlap_with_selected':round(alternative_overlap(c,p),3),'nutrition':nutrition_report(p,s.target)} for p in s.candidates if p is not c]})
        day=days.setdefault(str(s.slot_date),{'planned_target_kcal':0.,'actual_kcal':0.,'slots':0})
        day['planned_target_kcal']+=s.target.kcal;day['slots']+=1
        val=c.totals.get('kcal')
        day['actual_kcal']=None if val is None or day['actual_kcal'] is None else day['actual_kcal']+val
        previous.append(c)
    for day in days.values():
        day['planned_target_kcal']=round(day['planned_target_kcal'],1)
        if day['actual_kcal'] is not None:
            day['actual_kcal']=round(day['actual_kcal'],1)
            day['delta_kcal']=round(day['actual_kcal']-day['planned_target_kcal'],1)
        else:day['delta_kcal']=None
    return {'daily_planned_scope':days,'meals':rows,'main_protein_counts_lunch_dinner':dict(families),'recent_ingredient_reuse_ratio':round(reused/max(total,1),3)}


def adjacent_offer_overlap(slots):
    """相邻天（同餐次）备选候选菜品重合率（IMP-059 第 4 步诊断）。

    对每个餐次、每对相邻天：day+1 提供的非主食菜里，有多少比例是 day 已提供过的
    （按 base_dish_id 计），逐对取平均。比值越低，说明「换一换翻到的候选」跨天越不重复。
    """
    from .meal_templates import non_staple_base_ids
    by_meal: dict[str, dict[str, set]] = {}
    for s in slots:
        ids: set[str] = set()
        for c in s.candidates:
            ids |= non_staple_base_ids(c)
        by_meal.setdefault(s.meal_type, {})[str(s.slot_date)] = ids

    per_meal: dict[str, dict] = {}
    ratios: list[float] = []
    for meal_type, days in by_meal.items():
        ordered = sorted(days.items())
        pair_ratios: list[float] = []
        for (d0, a), (d1, b) in zip(ordered, ordered[1:]):
            if not b:
                continue
            pair_ratios.append(len(a & b) / len(b))
        per_meal[meal_type] = {
            "adjacent_pairs": len(pair_ratios),
            "avg_offer_repeat_ratio": round(sum(pair_ratios) / len(pair_ratios), 3) if pair_ratios else None,
        }
        ratios.extend(pair_ratios)
    return {
        "per_meal": per_meal,
        "overall_avg_offer_repeat_ratio": round(sum(ratios) / len(ratios), 3) if ratios else None,
    }


def balance_rotation_loss(candidate,current,slot,slots):
    if slot.meal_type not in ('午','晚'):return 0.
    from .quality import selected
    regular=[s for s in slots if s.meal_type in ('午','晚')]
    idx=next((i for i,s in enumerate(regular) if s is slot),None)
    if idx is None:return 0.
    prior=[selected(s) for s in regular[max(0,idx-3):idx]]
    later=[selected(s) for s in regular[idx+1:idx+4]]
    others=[main_family(c) for c in prior+later if c is not None]
    near=[main_family(c) for c in ([prior[-1]] if prior else [])+([later[0]] if later else []) if c is not None]
    def cost(c):
        f=main_family(c)
        return 0. if not f else .05*others.count(f)+.08*near.count(f)
    return max(0.,min(.25,cost(candidate)-cost(current)))
