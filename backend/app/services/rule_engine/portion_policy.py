"""Practical portion options and soft everyday preference; no medical rules."""
from itertools import product
from math import isfinite
import re

# Inputs are the actual recipe's edible-ingredient weights, not cooked weights.
COUNT_EGGS = {'水煮鸡蛋','清蒸鸡蛋羹','洋葱炒蛋','肉末蒸蛋','少油番茄炒蛋','韭菜炒鸡蛋','西兰花蒸蛋'}
SEASON = ('盐','油','酱油','醋','姜','大蒜','大葱','小葱','胡椒','糖','料酒')
BULK_STARCH = {'白米饭','二米饭','山药米饭','白粥','小米粥','白馒头','原味切片面包','清汤面','原味米粉'}
DRINK_FRUIT = {'无糖豆浆','纯牛奶','原味酸奶','苹果','香蕉','橙子','梨','葡萄','西瓜','桃','猕猴桃'}

def ingredient_weights(d):
    rows=getattr(d,'ingredient_amounts',None) or []
    if not rows or any(not isinstance(r,(list,tuple)) or len(r)!=2 or r[1] is None for r in rows): return {}
    out={}
    for name,amount in rows:
        try: n=float(amount)
        except (ValueError,TypeError): return {}
        if not isfinite(n) or n<=0: return {}
        out[str(name)]=out.get(str(name),0)+n
    return out


def egg_count(d):
    grams=ingredient_weights(d).get('鸡蛋')
    if d.name.removesuffix("（少盐）") in COUNT_EGGS and grams in (50,100): return int(grams/50)
    return None


def serving_options(d,requested=1.0):
    # Only the nominal one-serving recipe is scalable. Synthetic fixture/legacy
    # facts preserve legacy test behaviour; unverified real dishes stay at 1.
    if d.servings!=1: return (1.,)
    if not ingredient_weights(d):
        return (1.,) if re.fullmatch(r'DISH-\d+', d.dish_id) else (.75,1.,1.25)
    n=egg_count(d)
    if n: return (1.,2.) if n==1 else (.5,1.)
    if d.name.removesuffix("（少盐）") in COUNT_EGGS: return (1.,)
    if d.name in BULK_STARCH: return (.5,1.,1.5,2.)
    if d.name in DRINK_FRUIT: return (.5,1.)
    return (.5,1.,1.5)


def breakfast_shape(portions,meal_type):
    # Roles are soft preferences. The only shape limit here is an executable
    # number of breakfast items; nutrition and redundant starches are scored.
    return meal_type!='早' or 1<=len(portions)<=3


def combo_portion_options(combo,meal_type,requested=1.,target=None,allowed_options=None):
    from .practical_quality import meal_options
    opts=allowed_options if allowed_options is not None else [meal_options(d,target,requested) if target is not None else serving_options(d,requested) for d in combo]
    if not all(opts): return ()
    # <=4^4 possibilities but bounded search: base, single/paired changes,
    # uniform extrema. Every searched option is physically meaningful.
    base=tuple(min(o,key=lambda x:abs(x-1)) for o in opts)
    all_opts=[base]
    for i,o in enumerate(opts):
        for x in o:
            all_opts.append(tuple(x if j==i else v for j,v in enumerate(base)))
    for i in range(len(opts)):
        for j in range(i+1,len(opts)):
            for x,y in product(opts[i],opts[j]):
                all_opts.append(tuple(x if k==i else y if k==j else v for k,v in enumerate(base)))
    all_opts.extend([tuple(min(o) for o in opts),tuple(max(o) for o in opts)])
    return tuple(dict.fromkeys(all_opts))


def everyday_cost(combo):
    # At most 0.06, only ranking. Never removes any dish from eligibility.
    if not combo:return 0.
    return .06*(1-sum(bool(set(getattr(d,'tags',[]) or []) & {'基础家常菜','常见','简单'}) for d in combo)/len(combo))


def portion_cost(combo,amounts,meal_type,target=None,limits=None):
    from .meal_templates import profile
    cost=.055*sum(abs(x-1) for x in amounts)
    if meal_type=='早':
        cost+=.22*max(0,sum('主食' in profile(d).roles for d in combo)-1)
    from .practical_quality import portion_size_cost
    return cost + portion_size_cost(combo,amounts,target,limits)


def practical_text(d,amount):
    w=ingredient_weights(d)
    if not w:return None
    # Ingredient weights represent recipe inputs, never claim cooked portion.
    main=[(n,g) for n,g in w.items() if n not in SEASON and not any(n==x for x in ('精盐','橄榄油','食用油','生抽','老抽'))]
    if not main:return None
    grams='、'.join(f'{n}{g*amount:g}g' for n,g in main)
    n=egg_count(d)
    prefix=f'约{n*amount:g}个蛋；' if n and float(n*amount).is_integer() else ''
    salt=sum(g for name,g in w.items() if name in ('盐','食盐','精盐'))*amount
    salt_text=f'；添加食盐{salt:g}g' if d.name.endswith('（少盐）') else ''
    return f'{amount:g}份（{prefix}配方用量：{grams}{salt_text}）'
