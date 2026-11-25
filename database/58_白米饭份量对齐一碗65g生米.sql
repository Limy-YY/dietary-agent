-- 58_白米饭份量对齐一碗65g生米.sql
-- 2026-11-24 · 白米饭「1份」大米 50g → 65g，对齐「一碗 = 65g 生米 = 150g 熟米」口径。
--
-- 背景：午餐碳水目标偏高（约 137g）叠加谷物份量上限，导致「一主食+一荤+一素」结构
-- 配低能量健康菜（清蒸鱼/鸡胸/瘦牛肉/清汤）够不到碳水下限，被挤出候选池（菜品重复/用不全）。
-- 本迁移配合后端两处改动：
--   ① 谷物份量上限 120g→130g（practical_quality.py）
--   ② 宏量/能量区间从「硬淘汰」改「软约束」（candidates.py / meal_templates.py）
--
-- 幂等：白米饭大米已是 65g 时重复执行无副作用；updated_at 置 now() 用于触发 dish_facts 数据指纹失效。

UPDATE core.dish_ingredient
SET amount_g = 65
WHERE dish_id = 'DISH-121'
  AND ingredient_id = 531;

UPDATE core.dish
SET updated_at = now()
WHERE dish_id = 'DISH-121' AND NOT is_deleted;
