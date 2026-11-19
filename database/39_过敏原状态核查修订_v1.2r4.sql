--
-- 39_过敏原状态核查修订_v1.2r4.sql
-- 用途：复核 issue#14 列出的 6 条 allergen_status=未核查 食材，修订状态并刷新配料/菜式过敏原快照。
-- 口径：
--   CN-1274 燕麦片：按含麸质谷物记「已确认含」，allergens={麸质}（麸质/小麦过敏用户硬排除）。
--   CN-392 四季豆、CN-400 绿豆芽、FDC-169704 糙米饭、FDC-170420 青豌豆、FDC-173757 鹰嘴豆：
--     不在本库过敏原词表内，记「确认不含」，allergens=[]。
-- 前置：01 备份还原且已跑完既有迁移链（含 38 菜式扩充）。执行账号：postgres。幂等：可重复执行。
--

\set ON_ERROR_STOP on
\pset pager off

DO $$
DECLARE
    v_has boolean;
    v_can_write boolean;
BEGIN
    v_has := to_regclass('core.ingredient') IS NOT NULL
         AND to_regclass('core.dish') IS NOT NULL
         AND to_regclass('core.dish_ingredient') IS NOT NULL;
    IF NOT v_has THEN
        RAISE EXCEPTION 'core.ingredient / dish / dish_ingredient 未建：先还原 01 备份并跑完既有迁移链，再跑本脚本';
    END IF;
    v_can_write := has_table_privilege(current_user, 'core.ingredient', 'UPDATE');
    IF NOT v_can_write THEN
        RAISE EXCEPTION '当前用户 % 对 core.ingredient 无 UPDATE 权限，请换 postgres 执行', current_user;
    END IF;
END $$;

-- 0. 登记导入批次与迁移日志（幂等）
INSERT INTO audit.import_batch
  (import_batch_id, dataset_name, dataset_version, original_file_name, original_sha256,
   imported_at, imported_by, status, notes)
VALUES
  (5, '食材过敏原状态核查修订', 'v1.2r4-2026-11-19', '39_过敏原状态核查修订_v1.2r4.sql', '',
   now(), 'chenyuan', 'promoted',
   '复核 6 条未核查食材：燕麦片按含麸质谷物记已确认含（麸质）；四季豆、绿豆芽、糙米饭、青豌豆、鹰嘴豆确认不含；同步刷新配料与菜式过敏原快照。')
ON CONFLICT (import_batch_id) DO NOTHING;
SELECT setval('audit.import_batch_import_batch_id_seq',
              COALESCE((SELECT max(import_batch_id) FROM audit.import_batch), 0));

INSERT INTO audit.schema_migration (migration_id, description, applied_by)
VALUES ('2026-11-19-allergen-review-r4',
        '6 条未核查食材过敏原状态复核：燕麦片记麸质（已确认含），其余 5 种确认不含；刷新配料与菜式快照。',
        'chenyuan')
ON CONFLICT (migration_id) DO NOTHING;

-- 1. 修订食材主表（含 source_row 内的状态与过敏原文本快照）
WITH review(food_id, status, allergens) AS (
    VALUES
        ('CN-1274',    '已确认含', ARRAY['麸质']::text[]),
        ('CN-392',     '确认不含', ARRAY[]::text[]),
        ('CN-400',     '确认不含', ARRAY[]::text[]),
        ('FDC-169704', '确认不含', ARRAY[]::text[]),
        ('FDC-170420', '确认不含', ARRAY[]::text[]),
        ('FDC-173757', '确认不含', ARRAY[]::text[])
)
UPDATE core.ingredient i SET
    allergen_status = r.status,
    allergens       = r.allergens,
    source_row = jsonb_set(
        jsonb_set(i.source_row, '{allergen_status}', to_jsonb(r.status)),
        '{allergens}', to_jsonb(array_to_string(r.allergens, ','))),
    updated_at = now()
FROM review r
WHERE i.food_id = r.food_id AND NOT i.is_deleted;

-- 2. 刷新配料级快照 source_snapshot（两代格式：新键 allergens/allergen_status，旧键 original_*）
UPDATE core.dish_ingredient di SET
    source_snapshot = CASE
        WHEN di.source_snapshot ? 'original_allergens' THEN
            jsonb_set(
                jsonb_set(
                    jsonb_set(
                        jsonb_set(di.source_snapshot, '{allergens}', to_jsonb(i.allergens)),
                        '{allergen_status}', to_jsonb(i.allergen_status)),
                    '{original_allergens}', to_jsonb(i.allergens)),
                '{original_allergen_status}', to_jsonb(i.allergen_status))
        ELSE
            jsonb_set(
                jsonb_set(di.source_snapshot, '{allergens}', to_jsonb(i.allergens)),
                '{allergen_status}', to_jsonb(i.allergen_status))
    END
FROM core.ingredient i
WHERE di.ingredient_id = i.ingredient_id
  AND i.food_id IN ('CN-1274', 'CN-392', 'CN-400', 'FDC-169704', 'FDC-170420', 'FDC-173757');

-- 3a. 刷新菜式 avoid_snapshot 与 source_row.avoid（严格过敏原 / 未核查清单取自实时视图）
UPDATE core.dish d SET
    avoid_snapshot = jsonb_set(
        jsonb_set(COALESCE(d.avoid_snapshot, '{}'::jsonb),
                  '{strict_allergens}', to_jsonb(v.strict_allergens)),
        '{unverified_food_ids}', to_jsonb(v.unverified_food_ids)),
    source_row = jsonb_set(
        jsonb_set(COALESCE(d.source_row, '{}'::jsonb),
                  '{avoid,strict_allergens}', to_jsonb(v.strict_allergens)),
        '{avoid,unverified_food_ids}', to_jsonb(v.unverified_food_ids)),
    updated_at = now()
FROM app.v_dish_live_nutrition v
WHERE d.dish_id = v.dish_id
  AND EXISTS (
      SELECT 1 FROM core.dish_ingredient di
      JOIN core.ingredient i2 ON i2.ingredient_id = di.ingredient_id
      WHERE di.dish_id = d.dish_id
        AND i2.food_id IN ('CN-1274', 'CN-392', 'CN-400', 'FDC-169704',
                            'FDC-170420', 'FDC-173757'));

-- 3b. 同步 source_row.ingredients[] 内逐条配料的过敏原字段（关联子查询，不改顺序与其他键）
UPDATE core.dish d SET
    source_row = jsonb_set(d.source_row, '{ingredients}',
        (SELECT jsonb_agg(
                    CASE WHEN el->>'food_id' = i.food_id THEN
                             jsonb_set(jsonb_set(el, '{allergens}', to_jsonb(i.allergens)),
                                       '{allergen_status}', to_jsonb(i.allergen_status))
                         ELSE el END
                    ORDER BY ord)
         FROM jsonb_array_elements(d.source_row->'ingredients') WITH ORDINALITY AS t(el, ord)
         LEFT JOIN core.ingredient i ON i.food_id = el->>'food_id')),
    updated_at = now()
WHERE d.source_row ? 'ingredients'
  AND EXISTS (
      SELECT 1 FROM core.dish_ingredient di
      JOIN core.ingredient i2 ON i2.ingredient_id = di.ingredient_id
      WHERE di.dish_id = d.dish_id
        AND i2.food_id IN ('CN-1274', 'CN-392', 'CN-400', 'FDC-169704',
                            'FDC-170420', 'FDC-173757'));

-- 4. 自检：未核查清零、燕麦带出麸质、受影响菜式不再残留未核查标记、迁移登记 1 条
DO $$
DECLARE
    v_unchecked      integer;
    v_oats           integer;
    v_bad_unverified integer;
    v_oats_dish      integer;
    v_mig            integer;
BEGIN
    SELECT count(*) INTO v_unchecked
      FROM core.ingredient
     WHERE allergen_status = '未核查' AND NOT is_deleted;
    IF v_unchecked <> 0 THEN
        RAISE EXCEPTION '仍有 % 条未核查食材，应为 0', v_unchecked;
    END IF;

    SELECT count(*) INTO v_oats
      FROM core.ingredient
     WHERE food_id = 'CN-1274'
       AND allergen_status = '已确认含'
       AND allergens @> ARRAY['麸质'];
    IF v_oats <> 1 THEN
        RAISE EXCEPTION '燕麦片过敏原标记不正确，应为已确认含 + 麸质';
    END IF;

    SELECT count(*) INTO v_bad_unverified
      FROM app.v_dish_live_nutrition
     WHERE unverified_food_ids &&
           ARRAY['CN-1274', 'CN-392', 'CN-400', 'FDC-169704', 'FDC-170420', 'FDC-173757'];
    IF v_bad_unverified <> 0 THEN
        RAISE EXCEPTION '仍有 % 道菜式残留未核查配料标记', v_bad_unverified;
    END IF;

    SELECT count(*) INTO v_oats_dish
      FROM app.v_dish_live_nutrition
     WHERE dish_id IN ('DISH-030', 'DISH-059', 'DISH-117', 'DISH-118')
       AND NOT strict_allergens @> ARRAY['麸质'];
    IF v_oats_dish <> 0 THEN
        RAISE EXCEPTION '含燕麦片菜式未带出麸质过敏原，缺失 % 道', v_oats_dish;
    END IF;

    SELECT count(*) INTO v_mig
      FROM audit.schema_migration
     WHERE migration_id = '2026-11-19-allergen-review-r4';
    IF v_mig <> 1 THEN
        RAISE EXCEPTION '迁移登记缺失：2026-11-19-allergen-review-r4';
    END IF;

    RAISE NOTICE '39 核对通过：未核查食材 0 条，燕麦片记麸质，受影响菜式快照已刷新';
END $$;
