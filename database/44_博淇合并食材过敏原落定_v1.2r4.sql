--
-- 44_博淇合并食材过敏原落定_v1.2r4.sql
-- 用途：博淇 v21 合并带进的 3 条未核查食材（鸡腿 CN-882 / 白菜薹 CN-453 / 生菜 CN-483）
--       按 39 号先例「不在本库过敏原词表内 → 记确认不含」落定，并刷新受影响菜式的过敏原快照。
-- 前置：38~43 已入库且 v21 合并（DISH-121+ 段）已落地。执行账号：postgres。幂等：可重复执行。
--

\set ON_ERROR_STOP on
\pset pager off

BEGIN;

INSERT INTO audit.schema_migration (migration_id, description, applied_by)
VALUES ('2026-11-20-merge-ingredient-allergen-settle',
        '博淇 v21 合并带进的 3 条未核查食材（鸡腿 CN-882/白菜薹 CN-453/生菜 CN-483）按 39 先例落定为确认不含，并刷新受影响菜式过敏原快照',
        'merge-deploy')
ON CONFLICT (migration_id) DO NOTHING;

-- 1. 食材主表落定
UPDATE core.ingredient SET
    allergen_status = '确认不含',
    allergens = '{}'::text[],
    updated_at = now()
WHERE food_id IN ('CN-882','CN-453','CN-483') AND NOT is_deleted;

-- 2. 刷新受影响菜式的 avoid_snapshot（对齐实时视图，消除未核查标记残留）
UPDATE core.dish d SET
    avoid_snapshot = jsonb_set(
        jsonb_set(COALESCE(d.avoid_snapshot,'{}'::jsonb), '{strict_allergens}', to_jsonb(v.strict_allergens)),
        '{unverified_food_ids}', to_jsonb(v.unverified_food_ids)),
    updated_at = now()
FROM app.v_dish_live_nutrition v
WHERE d.dish_id = v.dish_id
  AND EXISTS (SELECT 1 FROM core.dish_ingredient di JOIN core.ingredient i2 ON i2.ingredient_id = di.ingredient_id
              WHERE di.dish_id = d.dish_id AND i2.food_id IN ('CN-882','CN-453','CN-483'));

COMMIT;
