"""Pure target parsing for plan, calendar date and meal slot; performs no writes."""
from dataclasses import dataclass
from datetime import date,timedelta
import re

NUM={'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10,
     **{c:i for i,c in enumerate('①②③④⑤⑥⑦⑧⑨⑩',1)}}
N=r'[0-9]+|[一二两三四五六七八九十①②③④⑤⑥⑦⑧⑨⑩]'
PLAN_RE=re.compile(rf'第\s*({N})\s*(?:份|个|套)(?:方案)?|方案\s*(?:第\s*)?({N})(?:号)?')
DAY_RE=re.compile(rf'第\s*({N})\s*天')
MEALS={'早餐':'早','早饭':'早','午餐':'午','午饭':'午','中餐':'午','晚餐':'晚','晚饭':'晚','早':'早','午':'午','晚':'晚'}

class ResolveError(ValueError):
    def __init__(self,code,message):super().__init__(message);self.code=code

@dataclass(frozen=True)
class Target:
    plan_index:int
    plan:dict
    slot:dict

def number(v):return int(v) if v.isascii() and v.isdigit() else NUM[v]
def plan_indices(text):return list(dict.fromkeys(number(m.group(1) or m.group(2)) for m in PLAN_RE.finditer(text or '')))
def meal_type(text,args=None):
    raw=(args or {}).get('meal_type')
    if raw:return MEALS.get(str(raw),str(raw))
    hits=list(dict.fromkeys(v for k,v in MEALS.items() if len(k)>1 and k in (text or '')))
    return hits[0] if len(hits)==1 else None

def _valid(y,m,d):
    try:return date(int(y),int(m),int(d)).isoformat()
    except ValueError as exc:raise ResolveError('DATA_INVALID','日期格式无效，请检查年月日') from exc

def scope_dates(text,slots,reference_date=None):
    """None means no date supplied; [] means supplied but outside this plan."""
    days=sorted({s.get('slot_date') for s in slots if s.get('slot_date')})
    text=text or '';ref=reference_date or date.today()
    nth=DAY_RE.search(text)
    if nth:
        i=number(nth.group(1))
        if not 1<=i<=len(days):return []
        return [days[i-1]]
    for word,delta in [('后天',2),('明天',1),('今天',0)]:
        if word in text:return [(ref+timedelta(days=delta)).isoformat()]
    ranged=re.search(r'(\d{1,2})月(\d{1,2})日?\s*(?:到|至|~|～|—|-)\s*(?:(\d{1,2})月)?(\d{1,2})日?',text)
    if not ranged:
        ranged=re.search(r'(\d{1,2})[./](\d{1,2})\s*(?:到|至|~|～|—|-)\s*(?:(\d{1,2})[./])?(\d{1,2})',text)
    if ranged:
        m1,d1,m2,d2=map(lambda x:int(x) if x else None,ranged.groups());m2=m2 or m1
        matched=[x for x in days if (date.fromisoformat(x).month,date.fromisoformat(x).day)>=(m1,d1)
                 and (date.fromisoformat(x).month,date.fromisoformat(x).day)<=(m2,d2)]
        return matched
    tokens=[];masked=list(text)
    patterns=[r'(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)',r'(?<!\d)(\d{4})年(\d{1,2})月(\d{1,2})日']
    for pattern in patterns:
        for m in re.finditer(pattern,text):
            tokens.append(_valid(*m.groups()))
            for i in range(m.start(),m.end()):masked[i]=' '
    rest=''.join(masked)
    for m in re.finditer(r'(?<!\d)(\d{1,2})[月./](\d{1,2})日?(?!\d)',rest):
        month,day=map(int,m.groups())
        found=[x for x in days if date.fromisoformat(x).month==month and date.fromisoformat(x).day==day]
        tokens.extend(found)
    if not tokens:
        has_date=bool(re.search(r'\d{4}年|\d{4}-\d|\d{1,2}[月./]\d{1,2}|今天|明天|后天|第.+天',text))
        return [] if has_date else None
    return list(dict.fromkeys(x for x in tokens if x in days))

def generation_scope(text,reference_date=None):
    """Parse an explicit new-plan range without needing an existing plan."""
    ref=reference_date or date.today();text=text or ''
    for word,delta in [('后天',2),('明天',1),('今天',0)]:
        if word in text:
            d=ref+timedelta(days=delta);return d.isoformat(),d.isoformat()
    full=[]
    for pattern in (r'(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)',r'(?<!\d)(\d{4})年(\d{1,2})月(\d{1,2})日'):
        full.extend(_valid(*m.groups()) for m in re.finditer(pattern,text))
    if full:return full[0],full[-1]
    ranged=re.search(r'(\d{1,2})月(\d{1,2})日?\s*(?:到|至|~|～|—|-)\s*(?:(\d{1,2})月)?(\d{1,2})日?',text)
    if not ranged:ranged=re.search(r'(\d{1,2})[./](\d{1,2})\s*(?:到|至|~|～|—|-)\s*(?:(\d{1,2})[./])?(\d{1,2})',text)
    if ranged:
        m1,d1,m2,d2=map(lambda x:int(x) if x else None,ranged.groups());m2=m2 or m1
        start=date(ref.year,m1,d1);end=date(ref.year,m2,d2)
        if end<start:end=date(ref.year+1,m2,d2)
        return start.isoformat(),end.isoformat()
    one=re.search(r'(?<!\d)(\d{1,2})[月./](\d{1,2})日?(?!\d)',text)
    if one:
        d=date(ref.year,*map(int,one.groups()));return d.isoformat(),d.isoformat()
    count=re.search(r'(?:接下来|未来)?\s*([二三四五六七2-7])天',text)
    if count:
        n=number(count.group(1));return ref.isoformat(),(ref+timedelta(days=n-1)).isoformat()
    return None

def resolve(plans,text,args=None,reference_date=None):
    args=args or {};indices=plan_indices(text)
    if len(indices)>1:raise ResolveError('AMBIGUOUS_TARGET','请唯一指定一份方案')
    if indices and not 1<=indices[0]<=len(plans):
        raise ResolveError('PLAN_NOT_FOUND',f'当前对话只有{len(plans)}份方案，请选择已有方案')
    candidates=[(indices[0],plans[indices[0]-1])] if indices else list(enumerate(plans,1))
    mt=meal_type(text,args);matches=[];date_supplied=False
    for i,plan in candidates:
        slots=plan.get('slots') or []
        dates=scope_dates(text,slots,reference_date);date_supplied|=dates is not None
        if dates==[]:continue
        for slot in slots:
            if mt and slot.get('meal_type')!=mt:continue
            if dates is not None and slot.get('slot_date') not in dates:continue
            matches.append(Target(i,plan,slot))
    if not matches:
        code='DATE_NOT_IN_PLAN' if date_supplied else 'SLOT_NOT_FOUND'
        raise ResolveError(code,'指定日期不在目标方案内' if date_supplied else '目标方案中没有对应餐次')
    plan_ids={str(x.plan.get('meal_plan_id') or x.plan.get('plan_id')) for x in matches}
    if len(plan_ids)>1:raise ResolveError('AMBIGUOUS_TARGET','多份方案都包含该日期和餐次，请说明方案编号')
    if len(matches)>1:raise ResolveError('AMBIGUOUS_TARGET','请明确目标日期或第几天及餐次')
    return matches[0]
