-- =====================================================================
-- 56 · 补维生素C：豆浆 / 鸡腿（动物性·豆类「确定不含维生素C」补 0）
-- =====================================================================
-- 背景：database/40「确定不含营养素补零」已把动物性/油脂/谷物/豆类/菌藻食材的维生素C 补 0，
--       但漏了 CN-338 豆浆（豆类）与 CN-882 鸡腿（禽肉），这两者 micro_nutrients.vitamin_c_mg 仍缺键（null）。
--       因 null≠0，含这两者的菜式维生素C 合计会变 null，报告显示「无完整天 / 不判达标」。
-- 口径：与 database/40 一致——动物性/豆类食材维生素C 确定为 0。
-- 幂等：仅补缺键行，已存在不覆盖；可重复执行。
-- =====================================================================

UPDATE core.ingredient
SET micro_nutrients = micro_nutrients || jsonb_build_object('vitamin_c_mg', 0),
    updated_at = now()
WHERE food_id IN ('CN-338', 'CN-882')
  AND NOT is_deleted
  AND (micro_nutrients ->> 'vitamin_c_mg') IS NULL;

-- 验证：应显示 2 行，vitamin_c_mg 均为 0
SELECT ingredient_id, food_id, name, micro_nutrients->>'vitamin_c_mg' AS vitamin_c_mg
FROM core.ingredient
WHERE food_id IN ('CN-338', 'CN-882') AND NOT is_deleted
ORDER BY food_id;
