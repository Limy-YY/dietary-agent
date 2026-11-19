"""Bounded in-process Agent context keyed by authenticated user and conversation."""
from contextlib import contextmanager
from dataclasses import dataclass,field
from threading import RLock
from time import monotonic
from uuid import uuid4

MAX_CONTEXTS=512
TTL_SECONDS=6*60*60

@dataclass
class Entry:
    state:dict=field(default_factory=lambda:{'current_plan':None,'plans':[],'v21_plans':[],'revision':0})
    lock:RLock=field(default_factory=RLock)
    touched:float=field(default_factory=monotonic)

_entries={}
_guard=RLock()

def normalize(user_id,conversation_id):
    user=str(user_id).strip()
    conv=str(conversation_id).strip() if conversation_id is not None else 'direct-'+uuid4().hex
    if not user or not conv:raise ValueError('缺少用户或会话标识')
    return user,conv

def _cleanup(now):
    stale=[]
    for k,v in _entries.items():
        if now-v.touched<=TTL_SECONDS:continue
        if v.lock.acquire(blocking=False):
            v.lock.release();stale.append(k)
    for k in stale:_entries.pop(k,None)
    if len(_entries)>MAX_CONTEXTS:
        need=len(_entries)-MAX_CONTEXTS
        for k,v in sorted(_entries.items(),key=lambda x:x[1].touched):
            if need<=0:break
            if v.lock.acquire(blocking=False):
                v.lock.release();_entries.pop(k,None);need-=1

@contextmanager
def locked(user_id,conversation_id):
    key=normalize(user_id,conversation_id);now=monotonic()
    with _guard:
        _cleanup(now);entry=_entries.setdefault(key,Entry());entry.touched=now
    with entry.lock:
        entry.touched=monotonic();entry.state['revision']=int(entry.state.get('revision') or 0)+1
        yield entry.state

def clear_for_tests():
    with _guard:_entries.clear()

