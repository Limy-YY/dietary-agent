\set ON_ERROR_STOP on
\pset pager off

-- 1. 结构与基础数据断言
DO $$
DECLARE
    v_missing text;
    v_count integer;
BEGIN
    SELECT string_agg(x.object_name, ', ' ORDER BY x.object_name)
    INTO v_missing
    FROM (
        VALUES
            ('core.goal_structure_map'),
            ('app.meal_slot'),
            ('app.meal_candidate'),
            ('app.meal_candidate_dish'),
            ('app.shopping_list'),
            ('app.nutrition_report'),
            ('app.nutrition_report_plan'),
            ('app.plan_adjustment'),
            ('audit.schema_migration')
    ) AS x(object_name)
    WHERE to_regclass(x.object_name) IS NULL;

    IF v_missing IS NOT NULL THEN
        RAISE EXCEPTION 'missing required tables: %', v_missing;
    END IF;

    SELECT count(*) INTO v_count FROM core.goal_structure_map WHERE is_active;
    IF v_count <> 5 THEN
        RAISE EXCEPTION 'expected 5 active goal mappings, found %', v_count;
    END IF;

    SELECT count(*) INTO v_count FROM app.v_key_micronutrient;
    IF v_count <> 7 THEN
        RAISE EXCEPTION 'expected 7 key micronutrients, found %', v_count;
    END IF;

    SELECT count(*) INTO v_count
    FROM core.ingredient
    WHERE data_quality NOT IN ('official', 'approx', 'check')
       OR data_quality IS NULL;
    IF v_count <> 0 THEN
        RAISE EXCEPTION 'invalid ingredient data_quality rows: %', v_count;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM audit.schema_migration
        WHERE migration_id = '2026-11-12-product-v2'
    ) THEN
        RAISE EXCEPTION 'schema migration marker is missing';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'diet_app') THEN
        RAISE EXCEPTION 'diet_app role is missing';
    END IF;
END
$$;

-- 2. 原数据保留与兼容迁移断言
DO $$
DECLARE
    v_count integer;
BEGIN
    SELECT count(*) INTO v_count FROM app.meal_plan WHERE data_version = 'legacy-v1.1';
    IF v_count < 3 THEN
        RAISE EXCEPTION 'legacy meal plans were not preserved; found %', v_count;
    END IF;

    SELECT count(*) INTO v_count FROM app.nutrition_report WHERE source_weekly_report_id IS NOT NULL;
    IF v_count < 1 THEN
        RAISE EXCEPTION 'legacy weekly nutrition report was not migrated';
    END IF;
END
$$;

-- 3. 全链路事务测试；最后ROLLBACK，不污染数据库
BEGIN;

INSERT INTO app.profile
    (user_id, name, gender, age, height_cm, weight_kg, goal_code,
     allergies, taboos, conditions, extras)
VALUES
    ('TEST-V2-MIGRATION-ROLLBACK', 'V2迁移验收', 'female', 30, 165, 55,
     'maintain', '{}', '{}', '{}', '{"is_test_data":true}')
RETURNING profile_id \gset

INSERT INTO app.meal_plan
    (user_id, plan_type, plan_date, start_date, end_date, status,
     macro_ratio, meals, sources, generation_request,
     micro_balance_window_start, micro_balance_window_end, agent_version)
VALUES
    ('TEST-V2-MIGRATION-ROLLBACK', '餐', DATE '2026-11-12',
     DATE '2026-11-12', DATE '2026-11-12', 'draft',
     '{"breakfast":0.30,"lunch":0.40,"dinner":0.30}', '[]',
     '{"is_test_data":true}', '生成一顿晚餐',
     DATE '2026-11-09', DATE '2026-11-11', 'agent-test-v2')
RETURNING meal_plan_id \gset

INSERT INTO app.meal_slot
    (meal_plan_id, slot_date, meal_type, target_macro)
VALUES
    (:meal_plan_id, DATE '2026-11-12', '晚餐',
     '{"protein_energy_pct":"10-20"}')
RETURNING meal_slot_id \gset

INSERT INTO app.meal_candidate
    (meal_slot_id, rank, why_text, macro_estimate, micro_estimate,
     sources, agent_output_version, explanation_generated_at)
VALUES
    (:meal_slot_id, 1, '验收候选1', '{"energy_kcal":500}',
     '{"calcium":200,"iron":4,"zinc":3,"vitamin_a":100,"vitamin_b1":0.4,"vitamin_b2":0.4,"vitamin_c":30}',
     '[{"source":"test"}]', 'agent-test-v2', now())
RETURNING candidate_id AS candidate_1_id \gset

INSERT INTO app.meal_candidate
    (meal_slot_id, rank, why_text, macro_estimate, micro_estimate,
     sources, agent_output_version, explanation_generated_at)
VALUES
    (:meal_slot_id, 2, '验收候选2', '{"energy_kcal":510}',
     '{"calcium":220,"iron":5,"zinc":3.5,"vitamin_a":120,"vitamin_b1":0.5,"vitamin_b2":0.5,"vitamin_c":35}',
     '[{"source":"test"}]', 'agent-test-v2', now())
RETURNING candidate_id AS candidate_2_id \gset

INSERT INTO app.meal_candidate_dish
    (candidate_id, dish_id, role, servings, estimated_g, portion_text, display_order)
SELECT :candidate_1_id, dish_id, '菜', 1, 200, '约一盘', 1
FROM core.dish ORDER BY dish_id LIMIT 1;

INSERT INTO app.meal_candidate_dish
    (candidate_id, dish_id, role, servings, estimated_g, portion_text, display_order)
SELECT :candidate_2_id, dish_id, '菜', 1, 220, '约一盘', 1
FROM core.dish ORDER BY dish_id OFFSET 1 LIMIT 1;

UPDATE app.meal_slot
SET selected_candidate_id = :candidate_1_id
WHERE meal_slot_id = :meal_slot_id;

UPDATE app.meal_plan
SET status = 'candidates'
WHERE meal_plan_id = :meal_plan_id;

INSERT INTO app.plan_adjustment
    (meal_plan_id, meal_slot_id, previous_candidate_id, new_candidate_id,
     instruction, nutrition_change, tool_name, tool_version)
VALUES
    (:meal_plan_id, :meal_slot_id, :candidate_1_id, :candidate_2_id,
     '换一个候选', '{"energy_kcal_delta":10}', 'replace_candidate', 'test-v2');

UPDATE app.meal_slot
SET selected_candidate_id = :candidate_2_id
WHERE meal_slot_id = :meal_slot_id;

UPDATE app.meal_plan
SET status = 'fixed'
WHERE meal_plan_id = :meal_plan_id;

INSERT INTO app.shopping_list (meal_plan_id, items)
VALUES (
    :meal_plan_id,
    '[{"ingredient_id":1,"name":"验收食材","estimated_quantity":200,"unit":"g"}]'
);

INSERT INTO app.nutrition_report
    (user_id, report_type, period_start, period_end, meal_plan_id,
     summary, macro_summary, key_micro_summary, completeness, sources)
VALUES
    ('TEST-V2-MIGRATION-ROLLBACK', 'plan', DATE '2026-11-12', DATE '2026-11-12',
     :meal_plan_id, '{"is_test_data":true}', '{"energy_kcal":510}',
     '{"calcium":{"value":220,"unit":"mg"}}', '{"status":"complete"}',
     '[{"source":"test"}]');

DO $$
BEGIN
    BEGIN
        UPDATE app.meal_candidate
        SET why_text = '不应允许修改'
        WHERE candidate_id = (
            SELECT s.selected_candidate_id
            FROM app.meal_plan p
            JOIN app.meal_slot s ON s.meal_plan_id = p.meal_plan_id
            WHERE p.user_id = 'TEST-V2-MIGRATION-ROLLBACK'
            ORDER BY p.meal_plan_id DESC
            LIMIT 1
        );
        RAISE EXCEPTION 'fixed-plan protection did not block candidate update';
    EXCEPTION
        WHEN SQLSTATE '55000' THEN
            NULL;
    END;
END
$$;

SELECT *
FROM app.recent_micro_balance(
    'TEST-V2-MIGRATION-ROLLBACK', DATE '2026-11-12', DATE '2026-11-12'
)
ORDER BY nutrient_id;

ROLLBACK;

-- 4. 输出验收摘要
SELECT 'schema_migration' AS check_item,
       count(*)::text AS result
FROM audit.schema_migration
WHERE migration_id = '2026-11-12-product-v2'
UNION ALL
SELECT 'ingredients', count(*)::text FROM core.ingredient WHERE NOT is_deleted
UNION ALL
SELECT 'dishes', count(*)::text FROM core.dish WHERE NOT is_deleted
UNION ALL
SELECT 'legacy_plans_preserved', count(*)::text FROM app.meal_plan WHERE data_version = 'legacy-v1.1'
UNION ALL
SELECT 'goal_mappings', count(*)::text FROM core.goal_structure_map WHERE is_active
UNION ALL
SELECT 'key_micronutrients', count(*)::text FROM app.v_key_micronutrient
UNION ALL
SELECT 'test_rows_after_rollback', count(*)::text FROM app.profile WHERE user_id = 'TEST-V2-MIGRATION-ROLLBACK'
ORDER BY check_item;


DO $$
DECLARE
    total_dishes integer;
    new_dishes integer;
    new_ingredient_rows integer;
    live_rows integer;
    bad_nutrition_rows integer;
    bad_amount_rows integer;
    bad_source_rows integer;
    bad_oil_salt_rows integer;
    duplicate_name_rows integer;
    orphan_rows integer;
    migration_rows integer;
BEGIN
    SELECT count(*) INTO total_dishes
    FROM core.dish
    WHERE NOT is_deleted;

    SELECT count(*) INTO new_dishes
    FROM core.dish
    WHERE dish_id BETWEEN 'DISH-031' AND 'DISH-060'
      AND NOT is_deleted;

    SELECT count(*) INTO new_ingredient_rows
    FROM core.dish_ingredient
    WHERE dish_id BETWEEN 'DISH-031' AND 'DISH-060';

    SELECT count(*) INTO live_rows
    FROM app.v_dish_live_nutrition
    WHERE dish_id BETWEEN 'DISH-031' AND 'DISH-060';

    SELECT count(*) INTO bad_nutrition_rows
    FROM app.v_dish_live_nutrition
    WHERE dish_id BETWEEN 'DISH-031' AND 'DISH-060'
      AND (
          NOT energy_complete
          OR NOT protein_complete
          OR NOT sodium_complete
          OR energy_kcal IS NULL
          OR protein_g IS NULL
          OR sodium_mg IS NULL
      );

    SELECT count(*) INTO bad_amount_rows
    FROM core.dish_ingredient
    WHERE dish_id BETWEEN 'DISH-031' AND 'DISH-060'
      AND amount_g <= 0;

    SELECT count(*) INTO bad_source_rows
    FROM core.dish
    WHERE dish_id BETWEEN 'DISH-031' AND 'DISH-060'
      AND (
          source IS NULL
          OR source_id IS NULL
          OR source_row ->> 'reference_source_url' IS NULL
          OR source_row ->> 'standardization_note' IS NULL
          OR source_row ->> 'data_quality' <> 'approx'
          OR jsonb_array_length(source_row -> 'ingredients') = 0
      );

    SELECT count(*) INTO bad_oil_salt_rows
    FROM (
        SELECT
            d.dish_id,
            d.default_oil_g,
            d.default_salt_g,
            COALESCE(sum(di.amount_g) FILTER (WHERE di.generated_from = 'oil_g'), 0) AS oil_g,
            COALESCE(sum(di.amount_g) FILTER (WHERE di.generated_from = 'salt_g'), 0) AS salt_g
        FROM core.dish d
        JOIN core.dish_ingredient di USING (dish_id)
        WHERE d.dish_id BETWEEN 'DISH-031' AND 'DISH-060'
        GROUP BY d.dish_id
    ) x
    WHERE x.default_oil_g <> x.oil_g
       OR x.default_salt_g <> x.salt_g;

    SELECT count(*) INTO duplicate_name_rows
    FROM (
        SELECT name
        FROM core.dish
        WHERE NOT is_deleted
        GROUP BY name
        HAVING count(*) > 1
    ) duplicate_names;

    SELECT count(*) INTO orphan_rows
    FROM core.dish_ingredient di
    LEFT JOIN core.dish d USING (dish_id)
    LEFT JOIN core.ingredient i USING (ingredient_id)
    WHERE di.dish_id BETWEEN 'DISH-031' AND 'DISH-060'
      AND (d.dish_id IS NULL OR i.ingredient_id IS NULL);

    SELECT count(*) INTO migration_rows
    FROM audit.schema_migration
    WHERE migration_id = '2026-11-13-dish-expansion-60';

    IF total_dishes <> 60 THEN
        RAISE EXCEPTION '有效菜式总数应为60，实际为%', total_dishes;
    END IF;
    IF new_dishes <> 30 THEN
        RAISE EXCEPTION '本批新增菜式应为30，实际为%', new_dishes;
    END IF;
    IF new_ingredient_rows <> 127 THEN
        RAISE EXCEPTION '本批配料关系应为127条，实际为%', new_ingredient_rows;
    END IF;
    IF live_rows <> 30 THEN
        RAISE EXCEPTION '新增菜在实时营养视图中应有30行，实际为%', live_rows;
    END IF;
    IF bad_nutrition_rows <> 0 THEN
        RAISE EXCEPTION '有%道新增菜缺少能量、蛋白质或钠的完整计算结果', bad_nutrition_rows;
    END IF;
    IF bad_amount_rows <> 0 THEN
        RAISE EXCEPTION '有%条新增配料用量不大于0', bad_amount_rows;
    END IF;
    IF bad_source_rows <> 0 THEN
        RAISE EXCEPTION '有%道新增菜缺少来源或标准化说明', bad_source_rows;
    END IF;
    IF bad_oil_salt_rows <> 0 THEN
        RAISE EXCEPTION '有%道新增菜的油盐字段与配料明细不一致', bad_oil_salt_rows;
    END IF;
    IF duplicate_name_rows <> 0 THEN
        RAISE EXCEPTION '有效菜式中存在%组重名', duplicate_name_rows;
    END IF;
    IF orphan_rows <> 0 THEN
        RAISE EXCEPTION '新增菜存在%条孤立配料关系', orphan_rows;
    END IF;
    IF migration_rows <> 1 THEN
        RAISE EXCEPTION '菜式扩充迁移记录应为1条，实际为%', migration_rows;
    END IF;
END
$$;

SELECT
    count(*) FILTER (WHERE NOT is_deleted) AS 有效菜式总数,
    count(*) FILTER (WHERE dish_id BETWEEN 'DISH-031' AND 'DISH-060' AND NOT is_deleted) AS 本批新增菜式
FROM core.dish;

SELECT
    category AS 类别,
    count(*) AS 新增数量
FROM core.dish
WHERE dish_id BETWEEN 'DISH-031' AND 'DISH-060'
GROUP BY category
ORDER BY category;

SELECT
    source_id AS 来源编号,
    count(*) AS 菜式数量
FROM core.dish
WHERE dish_id BETWEEN 'DISH-031' AND 'DISH-060'
GROUP BY source_id
ORDER BY source_id;

SELECT
    dish_id,
    name,
    ingredient_count,
    energy_kcal,
    protein_g,
    sodium_mg,
    strict_allergens,
    unverified_food_ids
FROM app.v_dish_live_nutrition
WHERE dish_id BETWEEN 'DISH-031' AND 'DISH-060'
ORDER BY dish_id;
