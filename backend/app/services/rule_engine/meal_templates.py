"""Reviewed default recommendation patterns for the 110-dish V2.1 catalogue.

This is culinary metadata, not an allergen or medical classifier. The mapping
is provisional until reviewed by the data team; safety remains in candidates.py.
Unknown production catalogue IDs are not silently classified as reviewed.
"""
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from itertools import combinations, product
import re

# id | exact current name | roles | breakfast use | staple kind | family
#    | commonness | complexity
# roles: S staple, P protein dish, V vegetable, T soup, D dairy, F fruit
# breakfast use: B sweet bowl, N neutral starch, E mild egg, L mild savory side,
# M milk/soy drink, F fruit, C savory breakfast anchor, - lunch/dinner default.
# commonness/complexity: 0 = common/simple, 1 = regular, 2 = specialty/complex.
_ROWS = '''001|蒜香清蒸鸡胸肉|P|-|-|鸡肉|1|1
002|西兰花鸡胸肉快炒|PV|-|-|鸡肉|1|1
003|番茄鸡胸肉|PV|-|-|鸡肉|1|1
004|蘑菇鸡胸肉快炒|PV|-|-|鸡肉|1|1
005|胡萝卜蒸鸡胸肉|PV|-|-|鸡肉|1|1
006|蒜香清蒸鳕鱼|P|-|-|鱼|1|1
007|番茄鳕鱼汤|PVT|-|-|鱼|1|1
008|清蒸三文鱼|P|-|-|鱼|1|1
009|西兰花虾仁快炒|PV|-|-|虾|1|1
010|番茄虾仁|PV|-|-|虾|1|1
011|芹菜甜椒炒虾仁|PV|-|-|虾|1|1
012|少油番茄炒蛋|PV|L|-|鸡蛋|1|1
013|菠菜鸡蛋汤|PVT|L|-|鸡蛋|1|1
014|西兰花蒸蛋|PV|E|-|鸡蛋|1|1
015|番茄豆腐汤|PVT|L|-|豆腐|1|1
016|小白菜豆腐汤|PVT|L|-|豆腐|1|1
017|蘑菇豆腐快炒|PV|-|-|豆腐|1|1
018|蒜香茄子蒸豆腐|PV|-|-|豆腐|1|1
019|芹菜炒牛肉|PV|-|-|牛肉|1|1
020|番茄洋葱炒牛肉|PV|-|-|牛肉|1|1
021|青椒洋葱炒猪肉|PV|-|-|猪肉|1|1
022|蒜蓉西兰花|V|-|-|西兰花|1|1
023|蒜蓉菠菜|V|-|-|菠菜|1|1
024|胡萝卜炒花椰菜|V|-|-|花椰菜|1|1
025|蒜蓉凉拌黄瓜|V|-|-|黄瓜|1|1
026|番茄黄瓜沙拉|V|L|-|黄瓜|1|1
027|西葫芦蘑菇快炒|V|-|-|西葫芦|1|1
028|四季豆炒胡萝卜|V|-|-|四季豆|1|1
029|糙米鹰嘴豆拌饭|SP|-|grain|鹰嘴豆|2|2
030|燕麦香蕉酸奶碗|SDF|B|sweet|燕麦|2|2
031|清蒸鲈鱼|P|-|-|鱼|1|1
032|白萝卜炖牛肉|PV|-|-|牛肉|1|1
033|番茄胡萝卜牛肉汤|PVT|-|-|牛肉|1|1
034|凉拌豆芽|V|L|-|豆芽|1|1
035|蒜泥茄子|V|-|-|茄子|1|1
036|清炒苦瓜|V|-|-|苦瓜|1|1
037|香菇炖鸡胸肉|PV|-|-|鸡肉|1|1
038|海带豆腐汤|PVT|L|-|豆腐|1|1
039|黄瓜甜椒炒鸡丁|PV|-|-|鸡肉|1|1
040|山药甜椒炒胡萝卜|V|-|-|山药|1|1
041|洋葱炒牛肉|PV|-|-|牛肉|1|1
042|韭菜炒鸡蛋|PV|L|-|鸡蛋|1|1
043|香菇炒油菜|V|L|-|油菜|1|1
044|白菜炖豆腐|PV|L|-|豆腐|1|1
045|紫菜蛋花汤|PVT|L|-|鸡蛋|1|1
046|山药米饭|S|-|grain|米饭|1|1
047|菜花胡萝卜炒里脊|PV|-|-|猪肉|1|1
048|冬瓜排骨玉米汤|PVT|-|-|猪肉|1|2
049|小米粥|S|C|porridge|小米|1|1
050|海带拌芹菜胡萝卜|V|L|-|海带|1|1
051|什锦蔬菜豆腐汤|PVT|L|-|豆腐|1|2
052|土豆茄子炖牛肉|PV|-|-|牛肉|1|2
053|玉米烩蛤蜊|P|-|-|贝类|2|2
054|芹菜拌花生|V|-|-|花生|2|1
055|番茄菠菜疙瘩汤|SVT|-|soupgrain|小麦|1|2
056|蒸红薯|S|N|tuber|红薯|1|1
057|蒸南瓜|S|N|tuber|南瓜|1|1
058|二米饭|S|-|grain|米饭|1|1
059|酸奶燕麦片|SD|B|sweet|燕麦|2|1
060|醋溜土豆丝|V|-|-|土豆|1|1
061|清蒸黄花鱼|P|-|-|鱼|1|0
062|清蒸带鱼|P|-|-|鱼|0|0
063|白灼鱿鱼|P|L|-|水产|2|0
064|草鱼豆腐汤|PT|L|-|鱼|1|1
065|鲫鱼白萝卜汤|PVT|-|-|鱼|1|1
066|鲤鱼炖冬瓜|PV|-|-|鱼|2|2
067|牡蛎豆腐羹|PT|L|-|鸡蛋|2|0
068|蛤蜊丝瓜汤|PVT|-|-|贝类|2|1
069|清蒸河蟹|P|-|-|水产|1|0
070|韭菜炒鱿鱼|PV|-|-|水产|2|1
071|冬瓜炖鸭肉|PV|-|-|鸭肉|2|2
072|白萝卜炖羊肉|PV|-|-|羊肉|2|2
073|葱爆羊肉|P|-|-|羊肉|1|0
074|菠菜炒猪肝|PV|-|-|内脏|2|1
075|番茄猪肝汤|PVT|-|-|内脏|2|1
076|彩椒里脊丝|PV|-|-|猪肉|1|0
077|胡萝卜炒里脊|PV|-|-|猪肉|1|1
078|白菜炖五花肉|PV|-|-|猪肉|2|2
079|洋葱炒猪肝|PV|-|-|内脏|2|1
080|芹菜炒鸭肉|PV|-|-|鸭肉|1|1
081|木耳炒肉片|PV|-|-|猪肉|1|1
082|牛肉炖土豆|PV|-|-|牛肉|2|2
083|豆腐干炒芹菜|PV|L|-|豆腐|1|1
084|腐竹烧冬瓜|PV|-|-|豆腐|2|2
085|豆腐皮拌黄瓜|PV|L|-|豆腐|1|1
086|青豌豆炒蛋|PV|E|-|鸡蛋|1|1
087|鹰嘴豆蔬菜沙拉|PV|-|-|豆制品|1|1
088|木耳炒蛋|PV|E|-|鸡蛋|1|1
089|洋葱炒蛋|PV|L|-|鸡蛋|0|0
090|菠菜拌豆腐|PV|L|-|豆腐|1|1
091|番茄豆腐烩|PV|L|-|豆腐|2|2
092|鸡蛋羹|P|-|-|鸡蛋|1|0
093|蒜蓉空心菜|V|-|-|-|1|0
094|莴笋炒木耳|V|-|-|-|1|1
095|清炒莲藕|V|-|-|-|1|1
096|金针菇拌黄瓜|V|L|-|-|1|1
097|蒜香茼蒿|V|-|-|-|1|0
098|蒜蓉苋菜|V|-|-|-|1|0
099|西葫芦烩木耳|V|-|-|-|2|2
100|竹笋炒香菇|V|-|-|-|1|1
101|番茄菜花|V|-|-|-|1|0
102|醋溜白菜|V|-|-|-|1|0
103|海带拌芹菜|V|L|-|-|1|1
104|黄豆芽炒韭菜|V|-|-|-|1|1
105|紫菜豆腐汤|PT|L|-|豆腐|1|1
106|丝瓜鸡蛋汤|PVT|-|-|鸡蛋|1|1
107|鲜蘑青菜汤|VT|-|-|-|1|1
108|番茄冬瓜汤|VT|-|-|-|1|1
109|山药木耳汤|VT|-|-|-|1|1
110|竹笋青菜汤|VT|-|-|-|1|1
111|萝卜丝海带汤|VT|-|-|-|1|1
112|空心菜菌菇汤|VT|-|-|-|1|1
113|番茄鸡蛋面|SPV|E|grain|鸡蛋|1|0
114|鸡丝青菜面|SPV|C|grain|鸡肉|1|0
115|蔬菜米粉|SV|C|grain|-|1|0
116|杂粮饭|S|-|grain|-|0|0
117|燕麦牛奶粥|SD|B|porridge|-|0|0
118|苹果燕麦酸奶碗|SDF|B|sweet|-|0|0
119|蒸玉米段|S|N|grain|-|0|0
120|南瓜糯米饭|S|N|tuber|-|0|2
121|白米饭|S|-|grain|米饭|0|0
122|白馒头|S|C|grain|小麦|0|0
123|原味切片面包|S|N|grain|小麦|0|0
124|蒸玉米|S|N|grain|玉米|0|0
125|清汤面|S|C|grain|小麦|0|0
126|原味米粉|S|C|grain|米粉|0|0
127|水煮鸡蛋|P|E|-|鸡蛋|0|0
128|无糖豆浆|P|M|-|大豆|0|0
129|纯牛奶|D|M|-|牛奶|0|0
130|原味酸奶|D|M|-|牛奶|0|0
131|苹果|F|F|-|苹果|0|0
132|香蕉|F|F|-|香蕉|0|0
133|橙子|F|F|-|橙子|0|0
134|梨|F|F|-|梨|0|0
135|葡萄|F|F|-|葡萄|0|0
136|西瓜|F|F|-|西瓜|0|0
137|桃|F|F|-|桃|0|0
138|猕猴桃|F|F|-|猕猴桃|0|0
139|卤鸡腿|P|-|-|鸡肉|0|1
140|白切鸡腿|P|-|-|鸡肉|0|0
141|清蒸豆腐|P|L|-|豆腐|0|0
142|白灼虾仁|P|-|-|虾|0|0
143|清蒸带鱼（家常版）|P|-|-|鱼|1|0
144|清炖鲤鱼|P|-|-|鱼|0|0
145|清蒸鸡蛋羹|P|E|-|鸡蛋|0|0
146|盐水菜心|V|L|-|菜心|0|0
147|白灼生菜|V|L|-|生菜|0|0
148|清炒生菜|V|-|-|生菜|0|0
149|蒜炒空心菜|V|-|-|空心菜|0|0
150|清炒丝瓜|V|-|-|丝瓜|0|0
151|白灼西兰花|V|L|-|西兰花|0|0
152|盐水小白菜|V|L|-|小白菜|0|0
153|清炒大白菜|V|-|-|大白菜|0|0
154|清炒油菜|V|-|-|油菜|0|0
155|清炒菜心|V|-|-|菜心|0|0
156|清炒茼蒿|V|-|-|茼蒿|0|0
157|清炒苋菜|V|-|-|苋菜|0|0
158|清炒西葫芦|V|-|-|西葫芦|0|0
159|蒸茄子|V|L|-|茄子|0|0
160|白灼菜花|V|L|-|菜花|0|0
161|洋葱炒蛋（家常版）|PV|E|-|鸡蛋|1|1
162|肉末蒸蛋|P|L|-|鸡蛋|0|1
163|香菇蒸鸡|PV|-|-|鸡肉|0|0
164|土豆炖鸡|PV|-|-|鸡肉|0|1
165|清炖鸡汤|PT|-|-|鸡肉|0|1
166|肉末豆腐|P|-|-|猪肉|0|1
167|小葱拌豆腐|P|L|-|豆腐|0|0
168|香煎豆腐|P|-|-|豆腐|0|1
169|蒸土豆|S|N|tuber|土豆|0|0
170|白粥|S|C|porridge|米饭|0|0'''
ROLE = dict(S='主食', P='蛋白质菜', V='蔬菜', T='汤羹', D='奶类', F='水果')

@dataclass(frozen=True)
class DishProfile:
    name: str
    roles: frozenset
    breakfast: str
    staple: str
    family: str
    commonness: int = 1
    complexity: int = 1
    reviewed: bool = True


def role_set(codes):
    roles = {ROLE[c] for c in codes}
    if len(roles - {'汤羹'}) > 1:
        roles.add('复合菜')
    return frozenset(roles)


CATALOG = {}
for row in _ROWS.splitlines():
    key, name, codes, breakfast, staple, family, *priority = row.split('|')
    commonness = int(priority[0]) if priority else (2 if key in {'029','030','053','054','059'} else 1)
    complexity = int(priority[1]) if len(priority) > 1 else (2 if key in {'029','030','048','051','052','053','055'} else 1)
    CATALOG['DISH-' + key] = DishProfile(
        name, role_set(codes), breakfast, staple, family, commonness, complexity
    )


def base_dish_id(value):
    return value[:-3] if re.fullmatch(r'DISH-\d{3}-LS',value) else value


def non_staple_base_ids(candidate):
    """Return exact non-staple identities used by a candidate.

    Low-salt variants share the base identity with the original dish, so a
    normal dish and its low-salt variant cannot masquerade as two different
    dishes within the same day. Unknown catalogue items are conservatively
    treated as non-staples until their culinary metadata is reviewed.
    """
    out = set()
    for dish_id in getattr(candidate, 'dish_ids', ()):
        base = base_dish_id(dish_id)
        known = CATALOG.get(base)
        if known is None or '主食' not in known.roles:
            out.add(base)
    return out


def profile(dish):
    base=base_dish_id(dish.dish_id)
    known = CATALOG.get(base)
    expected=known.name+('（少盐）' if base!=dish.dish_id else '') if known else None
    if known and expected == dish.name:
        return known
    # Unreviewed real catalogue dishes must be reviewed before default generation.
    # Legacy/non-catalogue sources have conservative role inference, explicitly marked.
    if known or re.fullmatch(r'DISH-\d+', dish.dish_id):
        return DishProfile(dish.name, frozenset({'未知'}), '-', '-', '', 2, 2, False)
    blob = ' '.join([dish.name or '', dish.category or '', *(dish.tags or []), *(dish.ingredient_names or [])])
    roles = set()
    if dish.is_staple or any(w in dish.name for w in ('燕麦','面包','馒头','粥')): roles.add('主食')
    if dish.is_soup or '汤' in dish.name: roles.add('汤羹')
    if any(w in blob for w in ('鸡','鸭','猪','牛肉','羊肉','鱼','虾','蛋','豆腐','豆干','蛤蜊','水产','肉类')): roles.add('蛋白质菜')
    if any(w in blob for w in ('蔬菜','菠菜','西兰花','白菜','芹菜','萝卜','番茄','黄瓜','茄子','油菜','香菇')): roles.add('蔬菜')
    if any(w in blob for w in ('酸奶','牛奶','奶酪')): roles.add('奶类')
    if any(w in blob for w in ('香蕉','水果','苹果')): roles.add('水果')
    sweet = '燕麦' in dish.name or '酸奶' in dish.name
    staple = 'sweet' if sweet else ('porridge' if '粥' in dish.name else 'grain') if '主食' in roles else '-'
    bf = 'B' if sweet else 'C' if staple != '-' else 'L' if roles & {'蛋白质菜','蔬菜'} else '-'
    if len(roles - {'汤羹'}) > 1: roles.add('复合菜')
    family = next((x for x, words in [('鸡肉',('鸡胸','鸡肉')),('鱼',('鱼',)),('豆腐',('豆腐',)),('鸡蛋',('鸡蛋',)),('猪肉',('猪','排骨')),('牛肉',('牛肉',)),('燕麦',('燕麦',))] if any(w in blob for w in words)), '')
    return DishProfile(dish.name, frozenset(roles or {'未知'}), bf, staple, family, 2, 2, False)


def dish_roles(dish):
    return profile(dish).roles


def template_for(combo, meal_type):
    """Describe a practical combination; roles inform ranking, not eligibility.

    Food safety, dietary exclusions and nutrient limits are enforced elsewhere.
    This function only rejects duplicate, unknown or impractically large meals.
    """
    if not combo or len({base_dish_id(d.dish_id) for d in combo}) != len(combo): return None
    ps = [profile(d) for d in combo]
    if any('未知' in p.roles for p in ps): return None
    # A single item is a meal only when it is itself a reviewed composite dish;
    # plain rice, one egg or one vegetable is not nutritionally complete enough.
    if len(ps) == 1 and '复合菜' not in ps[0].roles: return None
    if meal_type in ('早','加餐'):
        if len(ps) > 3: return None
        return '简易营养早餐' if len(ps) <= 2 else '灵活早餐搭配'
    if meal_type not in ('午','晚') or len(ps) > 4: return None
    roles = set().union(*(p.roles for p in ps))
    if {'蛋白质菜','蔬菜'} <= roles: return '蛋白质蔬菜搭配'
    if '复合菜' in roles: return '家常复合搭配'
    return '灵活家常搭配'


from itertools import combinations, product

def iter_template_combos(dishes, meal_type):
    """按餐盘结构分桶枚举，避免 C(N,3) 组合爆炸及双主食搭配。"""
    available = list({d.dish_id: d for d in dishes}.values())
    metas = {d.dish_id: profile(d) for d in available}
    def m(d): return metas[d.dish_id]

    if meal_type in ('早', '加餐'):
        eligible = [
            d for d in available if m(d).breakfast != '-'
            or (m(d).commonness == 0 and m(d).complexity == 0 and '蛋白质菜' in m(d).roles)
        ]
        bf_staples = [d for d in eligible if '主食' in m(d).roles]
        bf_non_staples = [d for d in eligible if '主食' not in m(d).roles]
        bf_proteins = [d for d in bf_non_staples if '蛋白质菜' in m(d).roles]
        bf_sides = [d for d in bf_non_staples if '蛋白质菜' not in m(d).roles]

        # 1道菜：仅复合主食（如燕麦香蕉酸奶碗）
        for s in bf_staples:
            if '复合菜' in m(s).roles and template_for((s,), meal_type):
                yield (s,)
        # 2道菜：1主食 + 1非主食，或 1蛋白 + 1配菜
        for combo in product(bf_staples, bf_non_staples):
            if template_for(combo, meal_type): yield combo
        for combo in product(bf_proteins, bf_sides):
            if template_for(combo, meal_type): yield combo
        # 3道菜：1主食 + 1蛋白 + 1配菜，或 1主食 + 2非蛋白配菜（如牛奶+水果）
        for combo in product(bf_staples, bf_proteins, bf_sides):
            if template_for(combo, meal_type): yield combo
        for s in bf_staples:
            for a, b in combinations(bf_sides, 2):
                if template_for((s, a, b), meal_type): yield (s, a, b)
        return

    # 午/晚餐按角色拆成 4 个互不重叠的桶
    savory = [
        d for d in available if m(d).breakfast not in ('B', 'M', 'F')
        and not m(d).roles & {'未知', '奶类', '水果'}
    ]
    pure_staples = [d for d in savory if '主食' in m(d).roles and len(m(d).roles - {'汤羹'}) == 1]
    staple_mains = [d for d in savory if '主食' in m(d).roles and len(m(d).roles - {'汤羹'}) > 1]
    proteins = [d for d in savory if '蛋白质菜' in m(d).roles and '主食' not in m(d).roles]
    veg_soups = [d for d in savory if '主食' not in m(d).roles and '蛋白质菜' not in m(d).roles]

    # 1道菜：仅允许自带主食的复合正餐（如糙米鹰嘴豆拌饭、疙瘩汤）
    for d in staple_mains:
        if template_for((d,), meal_type): yield (d,)
    # 2道菜：主食 + 蛋白质菜/复合主食，或 蛋白质菜 + 蔬菜/汤
    for combo in product(pure_staples, proteins + staple_mains):
        if template_for(combo, meal_type): yield combo
    for combo in product(proteins, veg_soups):
        if template_for(combo, meal_type): yield combo
    # 3道菜（剪枝核心）：1纯主食 × 1蛋白质主菜 × 1蔬菜/汤（从 62 万组直接降到约 4~5 万组）
    for combo in product(pure_staples, proteins, veg_soups):
        if template_for(combo, meal_type): yield combo
    for combo in product(staple_mains, proteins, veg_soups):
        if template_for(combo, meal_type): yield combo


def extension_combos(dishes, meal_type):
    """Bounded four-item expansion for real recipes only; never required."""
    if meal_type not in ('午','晚'):return
    ds=[d for d in dishes if getattr(d,'ingredient_amounts',None) and profile(d).reviewed]
    staples=[d for d in ds if profile(d).roles=={'主食'} and profile(d).staple!='sweet']
    mains=[d for d in ds if '蛋白质菜' in profile(d).roles and '主食' not in profile(d).roles and profile(d).breakfast!='M']
    sides=[d for d in ds if profile(d).roles=={'蔬菜'}]
    from .practical_quality import dietary_attributes
    sides.sort(key=lambda d:(profile(d).commonness, (getattr(d,'sodium_mg',None) or 0)/max(1,dietary_attributes([d],[1])['vegetable_g']),d.dish_id))
    extra=[d for d in sides if dietary_attributes([d],[1])['vegetable_g']>=60][:8]
    # Main plus one regular side and one extra side, using every eligible main
    # and rotating the normal vegetable pool rather than every 4-combination.
    for i,main in enumerate(mains):
        for j,staple in enumerate(staples):
            for k in range(min(8,len(sides))):
                a=sides[(i+j+k)%len(sides)]
                if not extra:continue
                b=extra[(i+j+2*k)%len(extra)]
                combo=(staple,main,a,b)
                if template_for(combo,meal_type):yield combo


def main_dish(combo):
    return next((d for d in combo if '蛋白质菜' in profile(d).roles and not profile(d).roles & {'主食','汤羹'}), next((d for d in combo if '蛋白质菜' in profile(d).roles and '主食' not in profile(d).roles), combo[0]))


def staple_key(candidate):
    return tuple(sorted(p.dish_id for p in candidate.portions if '主食' in profile(p.facts).roles))


def retain_pool(pool, limit):
    """Retain best candidates AND reserve breadth by anchor and main family."""
    limit = max(1, int(limit))
    if len(pool) <= limit: return pool
    groups = defaultdict(deque)
    preferred = pool[:max(1, limit//3)]
    seen = {tuple(sorted(c.dish_ids)) for c in preferred}
    for c in pool:
        if tuple(sorted(c.dish_ids)) in seen: continue
        main = main_dish([p.facts for p in c.portions])
        from .practical_quality import main_family
        veg=tuple(sorted({profile(p.facts).family for p in c.portions if profile(p.facts).roles=={'蔬菜'}}))
        groups[(main_family(c) or profile(main).family or main.dish_id,veg)].append(c)
    out = list(preferred)
    while groups and len(out) < limit:
        for key in list(groups):
            if len(out) >= limit: break
            q = groups[key]; out.append(q.popleft())
            if not q: del groups[key]
    from .practical_quality import candidate_priority
    return sorted(out,key=lambda c: (*candidate_priority(c),tuple(c.dish_ids)))


@dataclass(frozen=True)
class SelectionContext:
    """一个餐位排序前对「历史已选餐」做的一次性聚合，供 selection_key / repetition_cost 复用。

    排序键内部原本逐候选重扫 previous（O(pool×历史)）；本上下文把这些聚合量
    提前算一次，排序键内只做 O(1) 查表。字段分别对齐 previous / protein_previous / same_day。
    """
    rep_counts: dict
    rep_recent_counts: dict
    rep_adjacent: frozenset
    rep_veg_families: dict
    rep_prev_sweet: int
    dish_sets: tuple
    families: tuple
    recent_purchases: frozenset
    today_used: frozenset


def build_selection_context(previous, protein_previous, same_day):
    """按 selection_key / repetition_cost 需要的口径，把历史聚合量算一次。"""
    from .practical_quality import main_family, purchases

    recent = previous[-6:] if previous else []
    rep_counts = Counter(base_dish_id(d) for c in previous for d in c.dish_ids)
    rep_recent_counts = Counter(base_dish_id(d) for c in recent for d in c.dish_ids)
    rep_adjacent = frozenset(base_dish_id(d) for d in previous[-1].dish_ids) if previous else frozenset()
    rep_veg_families = Counter(profile(p.facts).family for c in previous for p in c.portions
                               if profile(p.facts).roles == {'蔬菜'})
    rep_prev_sweet = sum(profile(q.facts).staple == 'sweet' for c in previous for q in c.portions)
    dish_sets = tuple(frozenset(base_dish_id(d) for d in c.dish_ids) for c in previous)

    fam_src = protein_previous if protein_previous is not None else previous
    families = tuple(main_family(c) for c in fam_src)
    recent_purchases = frozenset().union(*(purchases(c) for c in previous[-4:]))
    today_used = frozenset().union(*(non_staple_base_ids(c) for c in same_day)) if same_day else frozenset()

    return SelectionContext(
        rep_counts=rep_counts, rep_recent_counts=rep_recent_counts,
        rep_adjacent=rep_adjacent, rep_veg_families=rep_veg_families,
        rep_prev_sweet=rep_prev_sweet, dish_sets=dish_sets, families=families,
        recent_purchases=recent_purchases, today_used=today_used,
    )


def selection_key(candidate, target, previous, repetition, *, protein_previous=None,
                  daily_energy_carry=0., same_day=None, ctx=None):
    # Never buy diversity at the cost of choosing a grossly off-target meal.
    deviation = abs(candidate.totals['kcal'] - target.kcal) / max(target.kcal,1)
    band = 0 if deviation <= .15 else 1 if deviation <= .25 else 2 if deviation <= .40 else 3
    keyset = frozenset(base_dish_id(d) for d in candidate.dish_ids)
    repeated = (sum(1 for ds in ctx.dish_sets if ds == keyset) if ctx is not None
                else sum(keyset == frozenset(base_dish_id(d) for d in c.dish_ids) for c in previous))
    # Family rotation and procurement are finite ranking terms; specialty is
    # never a categorical gate. Preserve the existing energy and exact-repeat bands.
    from .practical_quality import protein_rotation, purchase_credit
    if getattr(target,'meal_type',None) in ('午','晚'):
        src = previous if protein_previous is None else protein_previous
        rotation = (protein_rotation(candidate, src, families=ctx.families) if ctx is not None
                    else protein_rotation(candidate, src))
    else:
        rotation = 0.
    carry=max(-target.kcal*.12,min(target.kcal*.12,float(daily_energy_carry or 0.)))
    daily_energy_cost=.45*abs(candidate.totals['kcal']-(target.kcal+carry))/max(target.kcal,1)
    purchase = (purchase_credit(candidate, previous, recent_purchases=ctx.recent_purchases) if ctx is not None
                else purchase_credit(candidate, previous))
    overall_quality = candidate.score + repetition + rotation + daily_energy_cost - purchase
    if "macro_range_relaxed" in candidate.reason_codes:overall_quality+=.12
    from .practical_quality import candidate_priority
    tier=candidate_priority(candidate)[1]
    same_day_overlap = 0
    if same_day is not None:
        if ctx is not None:
            same_day_overlap = len(non_staple_base_ids(candidate) & ctx.today_used)
        else:
            used = set().union(*(non_staple_base_ids(c) for c in same_day)) if same_day else set()
            same_day_overlap = len(non_staple_base_ids(candidate) & used)
    # Structure first inside a reasonable energy range; nutrition remains a
    # score and gross deficit still loses. Within a usable energy/structure
    # band, avoid reusing an exact non-staple dish already served that day.
    if getattr(candidate,'score_breakdown',{}).get('attributes'):
        if same_day is not None:
            return (band>=2, tier>=2, bool(same_day_overlap), tier,
                    round(overall_quality+.25*repeated,4),band,tuple(candidate.dish_ids))
        return (band>=2,tier,round(overall_quality+.25*repeated,4),band,tuple(candidate.dish_ids))
    if same_day is not None:
        return (band, bool(same_day_overlap), repeated,
                'macro_range_relaxed' in candidate.reason_codes,
                round(overall_quality, 4), tuple(candidate.dish_ids))
    return (band, repeated, 'macro_range_relaxed' in candidate.reason_codes,
            round(overall_quality, 4), tuple(candidate.dish_ids))


def shortlist_combos(combos, target, relaxed, servings, diagnostics=None):
    """Cheap necessary bounds; strict and approximate search are both bounded.

    Strict search keeps the 2400 feasible combinations closest to the macro
    target (sorted by cheap distance) instead of scoring every feasible combo —
    scoring is O(portion options) and explodes once the catalogue grows.
    Approximate search retains up to 2400 with anchor/family coverage.
    """
    strict = []
    approx = []
    from .practical_quality import dietary_attributes,structure_tier
    from collections import Counter
    stats=diagnostics if diagnostics is not None else Counter()
    measures = [('energy_kcal',target.kcal*.85,target.kcal*1.15,target.kcal),
                ('protein_g',target.protein.low,target.protein.high,target.protein.target),
                ('fat_g',target.fat.low,target.fat.high,target.fat.target),
                ('carb_g',target.carb.low,target.carb.high,target.carb.target)]
    from .portion_policy import everyday_cost
    from .practical_quality import meal_options
    option_cache = {}
    for combo in combos:
        stats["combos_seen"]+=1
        for d in combo:
            if d.dish_id not in option_cache:
                option_cache[d.dish_id] = meal_options(d,target,servings)
        allowed = [option_cache[d.dish_id] for d in combo]
        if not all(allowed):
            stats["portion_bounds_rejected"]+=1;continue
        mins = [min(o) for o in allowed]
        maxs = [max(o) for o in allowed]
        if any(sum((getattr(d,attr) or 0)*lo for d,lo in zip(combo,mins)) > limit+.01
               for attr,limit in [('default_oil_g',target.oil_limit_g),('default_salt_g',target.salt_limit_g)]):
            stats['added_oil_salt_bounds_rejected']+=1;continue
        if any(getattr(d,'sodium_mg',None) is None for d in combo) or sum(d.sodium_mg*lo for d,lo in zip(combo,mins))*2.54/1000 > target.salt_limit_g+.01:
            stats['sodium_bounds_rejected']+=1;continue
        distance = 0.0
        feasible = True
        for attr,low,high,want in measures:
            values = [getattr(d,attr) for d in combo]
            if any(v is None for v in values):
                feasible=False; distance+=.3; continue
            lo = sum(v*s for v,s in zip(values,mins)); hi=sum(v*s for v,s in zip(values,maxs))
            # totals are rounded by the engine, allow small rounding margin.
            if hi < low-.1 or lo > high+.1: feasible=False
            distance += max(lo-want,want-hi,0)/max(want,1)
            distance += .12*abs(sum(values)*servings-want)/max(want,1)
        if not relaxed:
            if feasible: strict.append((distance, combo))
            else:stats["macro_bounds_rejected"]+=1
        elif all(d.energy_kcal is not None for d in combo):
            # Cheap structure-first ordering before expensive portion search.
            a=dietary_attributes(combo,[min(o,key=lambda v:abs(v-1)) for o in allowed])
            tier=structure_tier(a,target.meal_type) if all(getattr(d,'ingredient_amounts',None) for d in combo) else 0
            approx.append((tier*.75 + distance + everyday_cost(combo),tuple(d.dish_id for d in combo),combo))
    if not relaxed:
        strict.sort(key=lambda row: (row[0], tuple(sorted(d.dish_id for d in row[1]))))
        head = strict[:2400]
        stats["shortlisted"] += len(head)
        stats["search_budget_pruned"] += max(0, len(strict) - 2400)
        return [c for _, c in head]
    approx.sort(key=lambda row:(row[0],row[1]))
    stats["shortlisted"]+=min(2400,len(approx))
    stats["search_budget_pruned"]+=max(0,len(approx)-2400)
    if len(approx)<=2400: return [r[2] for r in approx]
    head=approx[:800]; groups=defaultdict(deque)
    for row in approx[800:]:
        combo=row[2]; a=combo[0]; m=main_dish(combo)
        groups[(a.dish_id,profile(m).family or m.dish_id)].append(row)
    while groups and len(head)<2400:
        for k in list(groups):
            if len(head)>=2400: break
            head.append(groups[k].popleft())
            if not groups[k]: del groups[k]
    return [r[2] for r in head]
