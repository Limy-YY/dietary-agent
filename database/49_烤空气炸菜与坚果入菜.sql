-- ============================================================================
-- 49 · 增补烤/空气炸菜 + 坚果入菜（窗口③ step3，2026-11-23）
-- 背景：评审报告 §一.1 CR008 烤/空气炸 0 菜使用；§二 坚果/种子 5 种只用了 1 种。
-- 本脚本新增 DISH-171..178 共 8 道：4 道烤/空气炸（鸡胸肉/豆腐/三文鱼/南瓜）+ 4 道坚果凉拌，
--   复活 3 种死食材（核桃 CN-743 / 杏仁 CN-752 / 芝麻 CN-773）。
-- 幂等可重跑（ON CONFLICT DO UPDATE / DO NOTHING）。前置：47 号（dish_meta 列）、48 号（fiber）。
-- 注意：check_catalog_sync.py（后端）仍按 _ROWS 断言，会在窗口② 把 profile() 迁到 dish_meta 前
--       对 171..178 报「目录缺失」——这是并行窗口的预期瞬态，dish_meta 已给齐，②迁库后即消除。
-- ============================================================================

BEGIN;

-- 0. 前置校验
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_schema='core' AND table_name='dish' AND column_name='dish_meta') THEN
    RAISE EXCEPTION 'core.dish.dish_meta 不存在：先跑 47 号脚本';
  END IF;
END $$;

-- 1. 登记迁移日志
INSERT INTO audit.schema_migration (migration_id, description, applied_by)
VALUES ('2026-11-23-roast-nut-supplement',
        '增补 DISH-171..178 共 8 道：4 道烤/空气炸 + 4 道坚果凉拌，复活核桃/杏仁/芝麻；幂等可重跑。',
        current_user)
ON CONFLICT (migration_id) DO NOTHING;

-- 2. import_batch
INSERT INTO audit.import_batch (dataset_name, dataset_version, original_file_name, original_sha256, imported_by, status, notes)
SELECT '烤空气炸与坚果入菜增量', '2026-11-23', '49_烤空气炸菜与坚果入菜.sql',
       'inline-20261123-roast-nut-supplement', current_user, 'promoted',
       '评审报告 §一.1/§二 缺口补充：CR008 烤/空气炸 0 菜 → 4 道；坚果入菜 4 道复活核桃/杏仁/芝麻。营养按 ingredient×amount_g 重算。'
WHERE NOT EXISTS (SELECT 1 FROM audit.import_batch WHERE dataset_name='烤空气炸与坚果入菜增量' AND dataset_version='2026-11-23');

CREATE TEMP TABLE _rn_batch ON COMMIT DROP AS
SELECT import_batch_id FROM audit.import_batch
WHERE dataset_name='烤空气炸与坚果入菜增量' AND dataset_version='2026-11-23'
ORDER BY import_batch_id LIMIT 1;

-- 3. 8 道新菜
INSERT INTO core.dish (
  dish_id, name, aliases, category, tags, method_text, cooking_rule_id,
  servings, default_oil_g, default_salt_g, cook_time_min,
  nutrition_snapshot, avoid_snapshot, source_row, import_batch_id, source, source_id
)
SELECT v.dish_id, v.name, ARRAY[]::text[], v.category, v.tags, v.method, v.rule_id,
       1, v.oil, v.salt, v.cook_min,
       '{}'::jsonb, '{}'::jsonb,
       jsonb_build_object('dish_id', v.dish_id, 'dish_name', v.name, 'category', v.category,
                          'method', v.method, 'servings', 1, 'oil_g', v.oil, 'salt_g', v.salt,
                          'cooking_rule_id', v.rule_id, 'data_quality', 'approx',
                          'nutrition_basis', 'core.ingredient × amount_g；缺失值保持NULL；未按烹饪损耗修正'),
       b.import_batch_id, '数据岗补充·烤/空气炸与坚果入菜', 'roast-nut-supplement-20261123'
FROM (VALUES
  ('DISH-171','空气炸鸡胸肉','畜禽肉类', ARRAY['烤','空气炸','低油']::text[], '空气炸', 'CR008', 2.0, 1.0, 15),
  ('DISH-172','空气炸豆腐','蛋豆类',     ARRAY['烤','空气炸','低油','植物蛋白']::text[], '空气炸', 'CR008', 3.0, 1.0, 12),
  ('DISH-173','烤三文鱼','水产类',       ARRAY['烤','清蒸']::text[], '烤', 'CR008', 2.0, 0.8, 15),
  ('DISH-174','烤南瓜','蔬菜类',         ARRAY['烤','空气炸','低油']::text[], '烤', 'CR008', 2.0, 0.5, 20),
  ('DISH-175','芹菜拌核桃仁','蔬菜类',   ARRAY['凉拌','坚果']::text[], '凉拌', 'CR007', 2.0, 0.8, 5),
  ('DISH-176','菠菜拌杏仁','蔬菜类',     ARRAY['凉拌','坚果']::text[], '凉拌', 'CR007', 2.0, 0.8, 5),
  ('DISH-177','核桃仁拌木耳','蔬菜类',   ARRAY['凉拌','坚果']::text[], '凉拌', 'CR007', 2.0, 0.8, 8),
  ('DISH-178','芝麻拌黄瓜','蔬菜类',     ARRAY['凉拌','坚果']::text[], '凉拌', 'CR007', 2.0, 0.8, 5)
) AS v(dish_id, name, category, tags, method, rule_id, oil, salt, cook_min)
CROSS JOIN _rn_batch b
ON CONFLICT (dish_id) DO UPDATE SET
  name=EXCLUDED.name, category=EXCLUDED.category, tags=EXCLUDED.tags,
  method_text=EXCLUDED.method_text, cooking_rule_id=EXCLUDED.cooking_rule_id,
  default_oil_g=EXCLUDED.default_oil_g, default_salt_g=EXCLUDED.default_salt_g,
  cook_time_min=EXCLUDED.cook_time_min, source_row=EXCLUDED.source_row, updated_at=now();

-- 4. 配料关系（food_id → ingredient_id）
INSERT INTO core.dish_ingredient (dish_id, ingredient_id, amount_g, cooked_amount_g, role, is_optional, generated_from, source_snapshot)
SELECT r.dish_id, i.ingredient_id, r.amount_g, NULL, r.role, false, 'roast_nut_supplement_20261123',
       jsonb_build_object('food_id', r.food_id, 'amount_g', r.amount_g, 'role', r.role,
                          'nutrition_basis', 'core.ingredient 每100g 按 amount_g 线性计算；未按烹饪损耗修正')
FROM (VALUES
  ('DISH-171','CN-880', 150, '主料'), ('DISH-171','CN-1510', 2, '烹调油'), ('DISH-171','CN-436', 5, '调味辅料'), ('DISH-171','CN-1565', 1.0, '食盐'),
  ('DISH-172','CN-333', 150, '主料'), ('DISH-172','CN-1510', 3, '烹调油'), ('DISH-172','CN-1518', 5, '调味料'), ('DISH-172','CN-436', 5, '调味辅料'), ('DISH-172','CN-1565', 1.0, '食盐'),
  ('DISH-173','CN-1052', 120, '主料'), ('DISH-173','CN-1510', 2, '烹调油'), ('DISH-173','CN-436', 5, '调味辅料'), ('DISH-173','CN-1565', 0.8, '食盐'),
  ('DISH-174','CN-426', 200, '主料'), ('DISH-174','CN-1510', 2, '烹调油'), ('DISH-174','CN-1565', 0.5, '食盐'),
  ('DISH-175','CN-479', 150, '主料'), ('DISH-175','CN-743', 15, '配料'), ('DISH-175','CN-1515', 2, '烹调油'), ('DISH-175','CN-1520', 5, '调味料'), ('DISH-175','CN-1565', 0.8, '食盐'),
  ('DISH-176','CN-473', 150, '主料'), ('DISH-176','CN-752', 15, '配料'), ('DISH-176','CN-1515', 2, '烹调油'), ('DISH-176','CN-1520', 5, '调味料'), ('DISH-176','CN-1565', 0.8, '食盐'),
  ('DISH-177','CN-579', 10,  '主料'), ('DISH-177','CN-743', 15, '配料'), ('DISH-177','CN-1515', 2, '烹调油'), ('DISH-177','CN-1520', 5, '调味料'), ('DISH-177','CN-436', 3, '调味辅料'), ('DISH-177','CN-1565', 0.8, '食盐'),
  ('DISH-178','CN-422', 150, '主料'), ('DISH-178','CN-773', 10, '配料'), ('DISH-178','CN-1515', 2, '烹调油'), ('DISH-178','CN-1520', 5, '调味料'), ('DISH-178','CN-436', 3, '调味辅料'), ('DISH-178','CN-1565', 0.8, '食盐')
) AS r(dish_id, food_id, amount_g, role)
JOIN core.ingredient i ON i.food_id = r.food_id AND NOT i.is_deleted
ON CONFLICT (dish_id, ingredient_id, role, generated_from) DO UPDATE SET
  amount_g=EXCLUDED.amount_g, source_snapshot=EXCLUDED.source_snapshot;

-- 5. dish_meta（供窗口② dish_meta 版 profile() 直接读取；全部进入生成池）
UPDATE core.dish AS d SET dish_meta = v.meta::jsonb
FROM (VALUES
  ('DISH-171', '{"roles":["P"],"breakfast":"-","staple":"-","family":"鸡肉","commonness":1,"complexity":0,"reviewed":true}'),
  ('DISH-172', '{"roles":["P"],"breakfast":"-","staple":"-","family":"豆腐","commonness":1,"complexity":0,"reviewed":true}'),
  ('DISH-173', '{"roles":["P"],"breakfast":"-","staple":"-","family":"鱼","commonness":1,"complexity":0,"reviewed":true}'),
  ('DISH-174', '{"roles":["V"],"breakfast":"-","staple":"-","family":"南瓜","commonness":1,"complexity":0,"reviewed":true}'),
  ('DISH-175', '{"roles":["V"],"breakfast":"L","staple":"-","family":"核桃","commonness":1,"complexity":0,"reviewed":true}'),
  ('DISH-176', '{"roles":["V"],"breakfast":"L","staple":"-","family":"杏仁","commonness":1,"complexity":0,"reviewed":true}'),
  ('DISH-177', '{"roles":["V"],"breakfast":"L","staple":"-","family":"核桃","commonness":1,"complexity":0,"reviewed":true}'),
  ('DISH-178', '{"roles":["V"],"breakfast":"L","staple":"-","family":"黄瓜","commonness":1,"complexity":0,"reviewed":true}')
) AS v(dish_id, meta)
WHERE d.dish_id = v.dish_id;

-- 6. 自检
DO $$
DECLARE n_dish int; n_rel int; n_meta int;
BEGIN
  SELECT count(*) INTO n_dish FROM core.dish WHERE source_id='roast-nut-supplement-20261123' AND NOT is_deleted;
  SELECT count(*) INTO n_rel FROM core.dish_ingredient di
   WHERE di.dish_id IN (SELECT dish_id FROM core.dish WHERE source_id='roast-nut-supplement-20261123');
  SELECT count(*) INTO n_meta FROM core.dish
   WHERE dish_id IN ('DISH-171','DISH-172','DISH-173','DISH-174','DISH-175','DISH-176','DISH-177','DISH-178') AND dish_meta IS NOT NULL;
  IF n_dish <> 8 THEN RAISE EXCEPTION '新增菜式应为 8，实为 %', n_dish; END IF;
  IF n_rel < 24 THEN RAISE EXCEPTION '配料关系应 ≥24 条，实为 %', n_rel; END IF;
  IF n_meta <> 8 THEN RAISE EXCEPTION 'dish_meta 应覆盖 8 道，实为 %', n_meta; END IF;
  RAISE NOTICE '新增 % 道菜 / % 条配料 / dish_meta % 条', n_dish, n_rel, n_meta;
END $$;

COMMIT;
