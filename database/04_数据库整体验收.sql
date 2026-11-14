\set ON_ERROR_STOP on
\pset pager off

-- =============================================================================
-- 04_数据库整体验收.sql（v1.2r1）
-- 执行前提：01 备份已恢复，且已执行 12_数据库整改_v1.2_to_v1.2r1.sql
-- 与 v1.2 版本相比新增：r1 整改项断言（P1-1 / P2-3 / P3）、被删测试视图的替代分支验收
-- =============================================================================

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

-- 1b. v1.2r1 整改项断言（对应评审 P1-1 / P2-3 / P3）
DO $$
DECLARE
    v_count integer;
    v_cols integer;
BEGIN
    -- P3：staging 暂存层不应出现在生产库
    IF to_regclass('staging.food_raw') IS NOT NULL THEN
        RAISE EXCEPTION 'staging schema is still present in production database';
    END IF;

    -- P3：硬编码虚构数据的测试视图不得留在生产库
    IF to_regclass('app.v_condition_rule_branch_acceptance') IS NOT NULL THEN
        RAISE EXCEPTION 'test view app.v_condition_rule_branch_acceptance is still present';
    END IF;

    -- r1 整改标记必须存在
    IF NOT EXISTS (
        SELECT 1 FROM audit.schema_migration
        WHERE migration_id = '2026-11-13-review-r1'
    ) THEN
        RAISE EXCEPTION 'r1 migration marker is missing; run 12_数据库整改 first';
    END IF;

    -- P1-1：conditions 契约函数与约束必须存在
    IF to_regprocedure('app.is_condition_map_valid(jsonb)') IS NULL THEN
        RAISE EXCEPTION 'app.is_condition_map_valid(jsonb) is missing';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'app.profile'::regclass
          AND conname = 'profile_conditions_contract_check'
    ) THEN
        RAISE EXCEPTION 'profile_conditions_contract_check is missing';
    END IF;

    -- P1-1：契约函数必须真的拦住 text[] 语义的取值
    IF app.is_condition_map_valid('["HTN"]'::jsonb) THEN
        RAISE EXCEPTION 'conditions contract does not reject array shape';
    END IF;
    IF app.is_condition_map_valid('{"HTN":{"status":"maybe"}}'::jsonb) THEN
        RAISE EXCEPTION 'conditions contract does not reject illegal status';
    END IF;
    IF NOT app.is_condition_map_valid('{"HTN":{"status":"confirmed","sodium_mg_target":1500}}'::jsonb) THEN
        RAISE EXCEPTION 'conditions contract rejects a legal condition map';
    END IF;

    -- P1-1：旧字段兜底读取视图必须存在
    IF to_regclass('app.v_profile_effective') IS NULL THEN
        RAISE EXCEPTION 'app.v_profile_effective is missing';
    END IF;

    -- P2-3：食材检索视图 25 列，且包含 4 个补列
    SELECT count(*) INTO v_cols
    FROM information_schema.columns
    WHERE table_schema = 'app' AND table_name = 'v_ingredient_search';
    IF v_cols <> 25 THEN
        RAISE EXCEPTION 'expected 25 columns on app.v_ingredient_search, found %', v_cols;
    END IF;

    SELECT count(*) INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'app' AND table_name = 'v_ingredient_search'
      AND column_name IN ('data_quality', 'source_note', 'iodine_ug', 'sfa_g');
    IF v_count <> 4 THEN
        RAISE EXCEPTION 'v_ingredient_search is missing r1 columns, found % of 4', v_count;
    END IF;

    -- P2-3 + R1：食材检索函数 18 个出参
    SELECT count(*) INTO v_cols
    FROM information_schema.parameters
    WHERE specific_schema = 'app'
      AND specific_name LIKE 'search_ingredients%'
      AND parameter_mode = 'OUT';
    IF v_cols <> 18 THEN
        RAISE EXCEPTION 'expected 18 OUT parameters on app.search_ingredients, found %', v_cols;
    END IF;

    SELECT count(*) INTO v_count
    FROM information_schema.parameters
    WHERE specific_schema = 'app'
      AND specific_name LIKE 'search_ingredients%'
      AND parameter_mode = 'OUT'
      AND parameter_name IN ('data_quality', 'source_note', 'iodine_ug', 'sfa_g', 'has_missing_macro');
    IF v_count <> 5 THEN
        RAISE EXCEPTION 'search_ingredients is missing r1 OUT columns, found % of 5', v_count;
    END IF;

    -- R1：函数必须带出 purine_level（视图与 v1.1 field_expose 都有这一列）
    SELECT count(*) INTO v_count
    FROM information_schema.parameters
    WHERE specific_schema = 'app'
      AND specific_name LIKE 'search_ingredients%'
      AND parameter_mode = 'OUT'
      AND parameter_name = 'purine_level';
    IF v_count <> 1 THEN
        RAISE EXCEPTION 'search_ingredients is missing purine_level (R1)';
    END IF;

    -- R1/R2 二轮整改标记
    IF NOT EXISTS (
        SELECT 1 FROM audit.schema_migration
        WHERE migration_id = '2026-11-13-review-r1b'
    ) THEN
        RAISE EXCEPTION 'r1b migration marker is missing (R1/R2); run 12_数据库整改 first';
    END IF;
END
$$;

-- 1c. P1-1 存量数据提示项（不抛错，只报告需要人工处理的旧数据）
SELECT count(*) AS conditions_存量总行数,
       count(*) FILTER (WHERE NOT app.is_condition_map_valid(conditions)) AS 形状不合规待修行数
FROM app.profile;

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

-- 2b. R2 断言：50–64 岁女性铁参考已并回单行取 12，且不再触发追问
DO $$
DECLARE
    v_count integer;
    v_value numeric;
    v_menstrual text;
BEGIN
    SELECT count(*), min(value), min(menstrual_status)
      INTO v_count, v_value, v_menstrual
      FROM core.nutrient_reference
     WHERE nutrient_id = 'iron'
       AND sex = 'female'
       AND age_group = '50-64'
       AND life_stage = '普通';

    IF v_count = 0 THEN
        RAISE EXCEPTION '50-64 岁女性铁参考行缺失；请确认 nutrient_reference 已导入并重跑 12_数据库整改';
    END IF;
    IF v_count <> 1 THEN
        RAISE EXCEPTION '50-64 岁女性铁参考应并回 1 行，实际 % 行（R2 未生效）', v_count;
    END IF;
    IF v_value <> 12 THEN
        RAISE EXCEPTION '50-64 岁女性铁参考值应为 12（保守侧），实际 %', v_value;
    END IF;
    IF nullif(v_menstrual, '') IS NOT NULL THEN
        RAISE EXCEPTION '50-64 岁女性铁参考应为通用行（menstrual_status 为空），实际 %', v_menstrual;
    END IF;

    SELECT count(*) INTO v_count
      FROM app.match_nutrient_reference('female', 660)
     WHERE nutrient_id = 'iron';
    IF v_count <> 1 THEN
        RAISE EXCEPTION '55 岁女性匹配铁参考应得 1 行，实际 % 行', v_count;
    END IF;

    IF EXISTS (
        SELECT 1 FROM app.match_nutrient_reference('female', 660)
        WHERE nutrient_id = 'iron' AND needs_clarification
    ) THEN
        RAISE EXCEPTION '55 岁女性未给月经状态时仍在追问（needs_clarification=true），R2 未生效';
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

-- 3b. P2-3 食材检索 5 字段实测（事务内插入 → 校验 → 随 ROLLBACK 清除）
DO $$
DECLARE
    v_batch bigint;
    v_source bigint;
    v_rows integer;
    v_iodine numeric;
    v_note text;
    v_dq text;
BEGIN
    INSERT INTO audit.import_batch (dataset_name, original_file_name, original_sha256)
    VALUES ('r1-acceptance', 'r1-acceptance.csv', 'acceptance')
    RETURNING import_batch_id INTO v_batch;

    INSERT INTO core.data_source (source_name, source_url, version, notes)
    VALUES ('r1-acceptance-source', 'https://example.org', 'acceptance', '来源表备注：验收用')
    RETURNING source_id INTO v_source;

    INSERT INTO core.ingredient
        (food_id, name, category, state, edible_portion_pct, energy_kcal, protein_g, fat_g,
         carbohydrate_g, sodium_mg, calcium_mg, sfa_g, micro_nutrients, source_url, source_id,
         source_row, import_batch_id, allergen_status, data_quality)
    VALUES
        ('R1-ACC-1', '验收西兰花', '蔬菜类', '生', 100, 34, 1.0, 0.5, 5.0, 10, 50, 0.1,
         '{"iodine_ug":"2.5"}', 'https://example.org/1', v_source,
         '{"source_note":"逐行来源备注"}', v_batch, '未核查', 'official');

    SELECT count(*) INTO v_rows FROM app.search_ingredients('验收西兰花', 5);
    IF v_rows <> 1 THEN
        RAISE EXCEPTION 'search_ingredients should return 1 row, got %', v_rows;
    END IF;

    SELECT r.iodine_ug, r.source_note, r.data_quality
    INTO v_iodine, v_note, v_dq
    FROM app.search_ingredients('验收西兰花', 5) r;

    IF v_dq IS DISTINCT FROM 'official' THEN
        RAISE EXCEPTION 'search_ingredients data_quality wrong: %', v_dq;
    END IF;
    IF v_iodine IS DISTINCT FROM 2.5::numeric THEN
        RAISE EXCEPTION 'search_ingredients iodine_ug wrong: %', v_iodine;
    END IF;
    IF v_note IS DISTINCT FROM '逐行来源备注' THEN
        RAISE EXCEPTION 'search_ingredients source_note wrong: %', v_note;
    END IF;
END
$$;

-- 3c. 疾病规则分支验收（替代已删除的 v_condition_rule_branch_acceptance 测试视图）
--     用真实规则 + 真实 profile 走一遍"已确诊 / 疑似不启用"分支。
DO $$
DECLARE
    v_rule_id text;
    v_condition_id text;
    v_status text;
BEGIN
    SELECT rule_id, condition_id INTO v_rule_id, v_condition_id
    FROM core.condition_nutrient_rule
    WHERE rule_kind IN ('nutrient_limit', 'nutrient_target')
    ORDER BY rule_id
    LIMIT 1;

    IF v_rule_id IS NULL THEN
        RAISE WARNING '条件规则表为空，跳过疾病规则分支验收';
        RETURN;
    END IF;

    -- confirmed：有规则但当天无摄入 → no_intake_data
    INSERT INTO app.profile (user_id, name, conditions)
    VALUES (
        'TEST-R1-BRANCH-CONFIRMED', '分支验收-已确诊',
        jsonb_build_object(v_condition_id, '{"status":"confirmed"}'::jsonb)
    );

    SELECT p.evaluation_status INTO v_status
    FROM app.preview_daily_condition_nutrient_rule(
        'TEST-R1-BRANCH-CONFIRMED', DATE '2026-11-12', v_rule_id
    ) p;

    IF v_status IS DISTINCT FROM 'no_intake_data' THEN
        RAISE EXCEPTION 'expected no_intake_data for confirmed condition without intake, got %', v_status;
    END IF;

    -- suspected：未确诊 → condition_not_active（规则不得启用）
    INSERT INTO app.profile (user_id, name, conditions)
    VALUES (
        'TEST-R1-BRANCH-SUSPECTED', '分支验收-疑似',
        jsonb_build_object(v_condition_id, '{"status":"suspected"}'::jsonb)
    );

    SELECT p.evaluation_status INTO v_status
    FROM app.preview_daily_condition_nutrient_rule(
        'TEST-R1-BRANCH-SUSPECTED', DATE '2026-11-12', v_rule_id
    ) p;

    IF v_status IS DISTINCT FROM 'condition_not_active' THEN
        RAISE EXCEPTION 'expected condition_not_active for suspected condition, got %', v_status;
    END IF;

    RAISE NOTICE 'branch acceptance passed with rule % / condition %', v_rule_id, v_condition_id;
END
$$;

ROLLBACK;

-- 4. 输出验收摘要
SELECT 'schema_migration' AS check_item,
       count(*)::text AS result
FROM audit.schema_migration
WHERE migration_id = '2026-11-12-product-v2'
UNION ALL
SELECT 'r1_migration', count(*)::text FROM audit.schema_migration WHERE migration_id = '2026-11-13-review-r1'
UNION ALL
SELECT 'r1b_migration', count(*)::text FROM audit.schema_migration WHERE migration_id = '2026-11-13-review-r1b'
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
SELECT 'staging_schema_removed', (to_regclass('staging.food_raw') IS NULL)::text
UNION ALL
SELECT 'test_view_removed', (to_regclass('app.v_condition_rule_branch_acceptance') IS NULL)::text
UNION ALL
SELECT 'test_rows_after_rollback', count(*)::text FROM app.profile WHERE user_id LIKE 'TEST-%'
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
