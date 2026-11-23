"""Practical portion options and soft everyday preference; no medical rules."""
from itertools import product
from math import isfinite
import re
from types import MappingProxyType

# Inputs are the actual recipe's edible-ingredient weights, not cooked weights.
COUNT_EGGS = {'水煮鸡蛋','清蒸鸡蛋羹','洋葱炒蛋','肉末蒸蛋','少油番茄炒蛋','韭菜炒鸡蛋','西兰花蒸蛋'}
SEASON = ('盐','油','酱油','醋','姜','大蒜','大葱','小葱','胡椒','糖','料酒')
BULK_STARCH = {'白米饭','二米饭','山药米饭','白粥','小米粥','白馒头','原味切片面包','清汤面','原味米粉'}
DRINK_FRUIT = {'无糖豆浆','纯牛奶','原味酸奶','苹果','香蕉','橙子','梨','葡萄','西瓜','桃','猕猴桃'}

def _parse_ingredient_weights(rows):
    """把 ingredient_amounts（[(食材名,克数),...]）解析成 {食材名: 克数}。

    任一行非法（非二元组 / 克数 None / 非有限 / <=0）→ 整体返回 {}（保守：宁可不用也不半用）。
    """
    if not rows or any(not isinstance(r,(list,tuple)) or len(r)!=2 or r[1] is None for r in rows): return {}
    out={}
    for name,amount in rows:
        try: n=float(amount)
        except (ValueError,TypeError): return {}
        if not isfinite(n) or n<=0: return {}
        out[str(name)]=out.get(str(name),0)+n
    return out


def ingredient_weights(d):
    """返回一道菜的 {食材名: 克数}（只读 Mapping）。结果缓存到 DishFacts 对象上，之后 O(1) 读取。

    ingredient_amounts 在请求内不可变（get_dish_facts 每请求只查一次），
    打分/排序/诊断的内层循环反复调本函数时不必再重新解析。
    返回只读视图：任何调用方就地修改都会抛 TypeError，避免误改共享缓存。
    """
    cached = getattr(d, 'ingredient_weights', None)
    if cached is None:
        cached = MappingProxyType(_parse_ingredient_weights(getattr(d,'ingredient_amounts',None) or []))
        try:
            d.ingredient_weights = cached
        except AttributeError:
            pass
    return cached


#: 非主料角色（§5.4）：按 dish_ingredient.role 剔除，取代 name 写死名单。
_NON_MAIN_ROLES = frozenset({'调味辅料', '调味料', '烹调油', '食盐'})


def main_ingredient_weights(d):
    """主料克数（§5.4）：按 dish_ingredient.role 剔除调味/油/盐。

    有 role 数据（连库）时按 role 过滤，保留主料/配料/配菜；无 role（离线源）回退
    ingredient_weights（全量）。返回只读 Mapping。
    """
    roles = getattr(d, 'ingredient_roles', None)
    if not roles:
        return ingredient_weights(d)
    cached = getattr(d, '_main_ingredient_weights', None)
    if cached is not None:
        return cached
    out = {}
    for name, amount, role in roles:
        if role in _NON_MAIN_ROLES:
            continue
        try:
            a = float(amount)
        except (TypeError, ValueError):
            continue
        if not isfinite(a) or a <= 0:
            continue
        out[str(name)] = out.get(str(name), 0) + a
    cached = MappingProxyType(out)
    try:
        d._main_ingredient_weights = cached
    except AttributeError:
        pass
    return cached


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
    if meal_type!='早':
        return True
    if not 1<=len(portions)<=3:
        return False
    from .meal_templates import profile
    metas=[profile(p.facts) for p in portions]
    # A breakfast must be recognised as breakfast food by the reviewed
    # catalogue. Full rice meals are intentionally lunch/dinner-only.
    if any(m.breakfast=='-' for m in metas):
        return False
    # Soup + fruit (and soup-heavy breakfast in general) was repeatedly chosen
    # only because its macros fit. It is not an executable default breakfast.
    if any('汤羹' in m.roles for m in metas):
        return False
    # Sweet bowls combine with milk/soy drink or fruit, not a cooked savoury
    # side. This prevents nutritionally valid but culinary incoherent拼盘.
    if any(m.staple=='sweet' for m in metas):
        return all(m.staple=='sweet' or m.breakfast in ('M','F') for m in metas)
    return True


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
    main_w=main_ingredient_weights(d)
    if not w:return None
    # Ingredient weights represent recipe inputs, never claim cooked portion.
    main=list(main_w.items())
    if not main:return None
    grams='、'.join(f'{n}{g*amount:g}g' for n,g in main)
    n=egg_count(d)
    prefix=f'约{n*amount:g}个蛋；' if n and float(n*amount).is_integer() else ''
    salt=sum(g for name,g in w.items() if name in ('盐','食盐','精盐'))*amount
    salt_text=f'；添加食盐{salt:g}g' if d.name.endswith('（少盐）') else ''
    return f'{amount:g}份（{prefix}配方用量：{grams}{salt_text}）'
