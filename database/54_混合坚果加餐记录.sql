-- ============================================================================
-- 54 · 混合坚果早餐加餐记录（2026-11-23）
-- 背景：坚果应「直接吃、混着吃、放早餐」，不塞进凉拌菜。新增 DISH-179「混合坚果」25g 加餐位。
--   配比：核桃 8g + 杏仁 7g + 花生仁 7g + 芝麻 3g = 25g。
--   营养快照（每 25g）：能量 146.9 / 蛋白 5.1 / 脂肪 12.2 / 碳水 5.7 / 纤维 2.3，
--   钠 2.3 / 钙 32.6 / 铁 0.9 / 锌 0.8（mg）。
-- 角色：roles=["G"]（坚果）+ breakfast="G"，早餐独立坚果加餐位，与水果位并存；tags 标「坚果」。
--   ⚠️ 口径待办：坚果脂肪密度高、须计入宏量（水果不计入）；引擎实现水果位时按 tags['坚果'] 区分。
-- 幂等可重跑（DELETE+INSERT）。前置：47 号（dish_meta / is_generation_enabled 列）。
-- ============================================================================

BEGIN;

-- 1. 登记迁移日志
INSERT INTO audit.schema_migration (migration_id, description, applied_by)
VALUES ('2026-11-23-mixed-nuts-snack',
        '新增 DISH-179 混合坚果 25g 早餐加餐位（核桃8+杏仁7+花生仁7+芝麻3）；幂等可重跑。',
        current_user)
ON CONFLICT (migration_id) DO NOTHING;

-- 2. import_batch
INSERT INTO audit.import_batch (dataset_name, dataset_version, original_file_name, original_sha256, imported_by, status, notes)
SELECT '混合坚果加餐位增量', '2026-11-23', '54_混合坚果加餐记录.sql',
       'inline-20261123-mixed-nuts-snack', current_user, 'promoted',
       '坚果直接吃/混着吃/放早餐：新增 25g 混合坚果（核桃8+杏仁7+花生仁7+芝麻3），营养按 ingredient×amount_g 加权。'
WHERE NOT EXISTS (SELECT 1 FROM audit.import_batch WHERE dataset_name='混合坚果加餐位增量' AND dataset_version='2026-11-23');

CREATE TEMP TABLE _mn_batch ON COMMIT DROP AS
SELECT import_batch_id FROM audit.import_batch
WHERE dataset_name='混合坚果加餐位增量' AND dataset_version='2026-11-23'
ORDER BY import_batch_id LIMIT 1;

-- 3. 删旧插新（幂等；先删配料再删菜，满足外键顺序）
DELETE FROM core.dish_ingredient WHERE dish_id='DISH-179';
DELETE FROM core.dish WHERE dish_id='DISH-179';

INSERT INTO core.dish (
  dish_id, name, aliases, category, tags, method_text, cooking_rule_id,
  servings, default_oil_g, default_salt_g, cook_time_min,
  nutrition_snapshot, avoid_snapshot, source_row, import_batch_id, source, source_id
)
SELECT 'DISH-179', '混合坚果', ARRAY[]::text[], '坚果类',
       ARRAY['基础家常菜','常见','简单','坚果','即食']::text[],
       '开袋即食，每天一小把（25g），可作早餐水果坚果位。',
       'CR001', 1, 0, 0, 0,
       '{"energy_kcal":146.9,"protein_g":5.1,"fat_g":12.2,"carbohydrate_g":5.7,"fiber_g":2.3,"sodium_mg":2.3,"calcium_mg":32.6,"iron_mg":0.9,"zinc_mg":0.8,"snapshot_date":"2026-11-23","ingredient_count":4,"calculation_basis":"core.ingredient × amount_g / 100","missing_value_policy":"任一配料对应字段缺失时，该菜该字段为NULL，不将缺失值视为0","cooking_loss_adjusted":false}'::jsonb,
       '{}'::jsonb,
       jsonb_build_object('dish_id','DISH-179','dish_name','混合坚果','category','坚果类',
                          'servings',1,'blend','核桃8g+杏仁7g+花生仁7g+芝麻3g',
                          'data_quality','official/approx','nutrition_basis','core.ingredient 每100g 按 amount_g 加权；缺失值保持NULL；未按烹饪损耗修正'),
       b.import_batch_id, '数据岗补充·混合坚果加餐', 'mixed-nuts-snack-20261123'
FROM _mn_batch b;

-- 4. 配料关系（food_id → ingredient_id；四坚果均为主料）
INSERT INTO core.dish_ingredient (dish_id, ingredient_id, amount_g, cooked_amount_g, role, is_optional, generated_from, source_snapshot)
SELECT 'DISH-179', i.ingredient_id, r.amount_g, NULL, '主料', false, 'mixed_nuts_snack_20261123',
       jsonb_build_object('food_id', r.food_id, 'amount_g', r.amount_g, 'role', '主料',
                          'nutrition_basis', 'core.ingredient 每100g 按 amount_g 线性计算；未按烹饪损耗修正')
FROM (VALUES
  ('CN-743', 8), ('CN-752', 7), ('CN-763', 7), ('CN-773', 3)
) AS r(food_id, amount_g)
JOIN core.ingredient i ON i.food_id = r.food_id AND NOT i.is_deleted;

-- 5. dish_meta（role F + breakfast F = 早餐水果坚果位，进入生成池）
UPDATE core.dish
SET dish_meta = '{"roles":["G"],"breakfast":"G","staple":"-","family":"坚果","commonness":1,"complexity":0,"reviewed":true}'::jsonb,
    updated_at = now()
WHERE dish_id = 'DISH-179';

-- 5b. 刷新 DISH-179 的 avoid_snapshot（对齐实时视图；新菜插入时快照为空，04 会判为不一致）
UPDATE core.dish d SET
    avoid_snapshot = jsonb_set(
        jsonb_set(COALESCE(d.avoid_snapshot,'{}'::jsonb), '{strict_allergens}', to_jsonb(v.strict_allergens)),
        '{unverified_food_ids}', to_jsonb(v.unverified_food_ids)),
    updated_at = now()
FROM app.v_dish_live_nutrition v
WHERE d.dish_id = v.dish_id AND d.dish_id = 'DISH-179';

-- 6. 自检
DO $$
DECLARE n_dish int; n_rel int; n_meta int; n_bad_snap int;
BEGIN
  SELECT count(*) INTO n_bad_snap
    FROM core.dish d JOIN app.v_dish_live_nutrition v USING (dish_id)
   WHERE d.dish_id = 'DISH-179'
     AND COALESCE(d.avoid_snapshot -> 'strict_allergens', '[]'::jsonb) <> COALESCE(to_jsonb(v.strict_allergens), '[]'::jsonb);
  IF n_bad_snap <> 0 THEN RAISE EXCEPTION 'DISH-179 过敏原快照与视图不一致：% 道', n_bad_snap; END IF;
  SELECT count(*) INTO n_dish FROM core.dish WHERE dish_id='DISH-179' AND NOT is_deleted AND is_generation_enabled;
  SELECT count(*) INTO n_rel FROM core.dish_ingredient WHERE dish_id='DISH-179';
  SELECT count(*) INTO n_meta FROM core.dish WHERE dish_id='DISH-179' AND dish_meta IS NOT NULL;
  IF n_dish <> 1 THEN RAISE EXCEPTION 'DISH-179 应存在且启用，实为 %', n_dish; END IF;
  IF n_rel <> 4 THEN RAISE EXCEPTION '配料应 4 条，实为 %', n_rel; END IF;
  IF n_meta <> 1 THEN RAISE EXCEPTION 'dish_meta 应覆盖，实为 %', n_meta; END IF;
  RAISE NOTICE '混合坚果：% 道 / % 条配料 / dish_meta % 条', n_dish, n_rel, n_meta;
END $$;

COMMIT;
