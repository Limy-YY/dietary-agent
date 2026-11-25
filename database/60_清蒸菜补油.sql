-- 60_清蒸菜补油.sql
-- 2026-11-24 · 清蒸（CR002）0 油菜补默认油 1.5g，对齐做法规则 oil_g_default。
--
-- 背景：清蒸荤/蛋/豆腐/蔬菜菜的 default_oil_g 被填成 0，而 core.cooking_rule 里
-- CR002「清蒸」的 oil_g_default=1.5（min=0, max=3）。0 油 → 整道菜能量偏低，
-- 是「清淡菜进不了候选池」的一个因素（主因仍是能量目标偏高，见规则引擎诊断）。
--
-- 口径：
--   - 只补「清蒸」规则（CR002）且当前 0 油的菜；
--   - 排除 5 道清蒸主食（蒸红薯/蒸南瓜/蒸玉米段/蒸玉米/蒸土豆）——主食本不放油；
--   - 生食/白灼/汤煮/水煮/凉拌等其它 0 油菜不在本次范围（另行决定）。
-- 幂等：仅 0 油菜被置 1.5，重复执行无副作用；touch updated_at 触发 dish_facts 指纹失效。

UPDATE core.dish d
SET default_oil_g = cr.oil_g_default,
    updated_at = now()
FROM core.cooking_rule cr
WHERE d.cooking_rule_id = cr.rule_id
  AND cr.rule_id = 'CR002'
  AND (d.default_oil_g IS NULL OR d.default_oil_g = 0)
  AND d.dish_id NOT IN ('DISH-056', 'DISH-057', 'DISH-119', 'DISH-124', 'DISH-169')
  AND NOT d.is_deleted;
