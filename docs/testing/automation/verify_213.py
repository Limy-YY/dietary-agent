# -*- coding: utf-8 -*-
"""#17 复验：213 口径落库后独立对账（走公网 API）"""
import json, os, sys, urllib.request, collections

BASE = os.environ["LIVE_BASE_URL"].rstrip("/")
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))

def _token():
    env = os.getenv("LIVE_TOKEN")
    if env:
        return env
    import jwt
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": "TEST-E2E-01", "iat": now, "exp": now + timedelta(minutes=1440)},
                      "change-me-in-production", algorithm="HS256")

TOKEN = _token()

def get(path):
    req = urllib.request.Request(BASE + path, headers={
        "Authorization": f"Bearer {TOKEN}", "Accept": "application/json"})
    r = json.load(op.open(req, timeout=30))
    return r.get("data", r)

dishes = []
p = 1
total = None
while True:
    r = get(f"/api/dishes/search?page={p}&page_size=100")
    total = r.get("total")
    items = r.get("items") or []
    dishes += items
    if len(dishes) >= total or not items:
        break
    p += 1

fails = []
def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (" | " + detail if detail else ""))
    if not cond:
        fails.append(name)

# ① 总数口径
nLS = [d for d in dishes if not d.get("dish_id","").endswith("-LS")]
ls  = [d for d in dishes if d.get("dish_id","").endswith("-LS")]
check("total=213", total == 213, f"api_total={total}")
check("total=213(全量对账)", len(dishes) == 213, f"fetched={len(dishes)}")
check("nLS=170", len(nLS) == 170, f"nLS={len(nLS)}")
check("LS=43", len(ls) == 43, f"LS={len(ls)}")

# ② 编号无撞号：121~170 全部存在且唯一；061~120 与 121~170 无重叠
ids = [d["dish_id"] for d in nLS]
rng121 = [i for i in ids if i.startswith("DISH-") and i[5:].isdigit() and 121 <= int(i[5:]) <= 170]
rng061_120 = [i for i in ids if i.startswith("DISH-") and i[5:].isdigit() and 61 <= int(i[5:]) <= 120]
check("DISH-121..170 共50且无重复", len(rng121) == 50 and len(set(rng121)) == 50, f"n={len(rng121)} uniq={len(set(rng121))}")
check("DISH-061..120 共60(陈媛版)", len(rng061_120) == 60, f"n={len(rng061_120)}")

# ③ 两道家常版与库内同名菜可区分
names = collections.defaultdict(list)
for d in nLS:
    names[d.get("name","")].append(d["dish_id"])
for nm in ["清蒸带鱼（家常版）", "洋葱炒蛋（家常版）"]:
    check(f"{nm} 存在", nm in names, f"ids={names.get(nm, [])}")
check("原 清蒸带鱼/洋葱炒蛋 仍在", "清蒸带鱼" in names and "洋葱炒蛋" in names,
      f"{names.get('清蒸带鱼', [])}/{names.get('洋葱炒蛋', [])}")

# ④ 43 条 LS 1:1 挂源菜
base_ids = set(ids)
orphan = [d["dish_id"] for d in ls if d["dish_id"][:-3] not in base_ids]
check("43 条 LS 均有源菜(1:1)", len(orphan) == 0, f"orphan={orphan}")

# ⑤ 新增 50 道营养/配料空值抽查
new50 = [d for d in dishes if d["dish_id"] in rng121]
bad_ing = [d["dish_id"] for d in new50 if not d.get("ingredient_count")]
bad_kcal = [d["dish_id"] for d in new50 if d.get("energy_kcal") in (None, "", 0)]
check("新增50道配料非空", len(bad_ing) == 0, f"bad={bad_ing[:5]}")
check("新增50道能量非空/非0", len(bad_kcal) == 0, f"bad={bad_kcal[:5]}")

# source_id 分组
grp = collections.Counter(d.get("source_id","?") for d in dishes)
print("source_id 分组:", dict(grp))

print(f"\n== 复验结束: {'全部通过' if not fails else f'{len(fails)} 项 FAIL: {fails}'} ==")
sys.exit(1 if fails else 0)
