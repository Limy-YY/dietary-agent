-- =====================================================================
-- 55 · 补维生素A：豆浆 / 白菜薹 / 生菜（植物性食材 preformed retinol = 0）
-- =====================================================================
-- 背景：这三个食材在食物成分表导入时 `micro_nutrients.vitamin_a_ug` 缺键（null），
--       而其余植物性食材（大米/玉米/西兰花/苋菜/小白菜等）该键均为 0（存「预成型
--       维生素A/视黄醇」，胡萝卜素另存 carotene_ug，不折算——见 IMP-042）。
--       因 null≠0，含这三者的菜式（如「清炒菜心」用白菜薹）维生素A 合计会变 null，
--       方案报告该营养素显示「无完整天 / 不判达标」。
-- 口径：与现有植物性食材对齐，补 0（不折算胡萝卜素，后续由 IMP-042 统一处理 RE vs RAE）。
-- 幂等：仅补缺键行，已存在不覆盖；可重复执行。
-- =====================================================================

UPDATE core.ingredient
SET micro_nutrients = micro_nutrients || jsonb_build_object('vitamin_a_ug', 0),
    updated_at = now()
WHERE food_id IN ('CN-338', 'CN-453', 'CN-483')
  AND NOT is_deleted
  AND (micro_nutrients ->> 'vitamin_a_ug') IS NULL;

-- 验证：应显示 3 行，vitamin_a_ug 均为 0
SELECT ingredient_id, food_id, name, micro_nutrients->>'vitamin_a_ug' AS vitamin_a_ug,
       micro_nutrients->>'carotene_ug' AS carotene_ug
FROM core.ingredient
WHERE food_id IN ('CN-338', 'CN-453', 'CN-483') AND NOT is_deleted
ORDER BY food_id;
