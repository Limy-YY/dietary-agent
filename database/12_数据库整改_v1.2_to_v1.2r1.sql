--
-- 12_数据库整改_v1.2_to_v1.2r1.sql
-- 用途：把评审接收的 v1.2 库就地整改为 v1.2r1。对 01 备份恢复后的库执行一次即可；
--       脚本整体幂等，可重复执行（重复执行不会报错、不会重复造对象、不会重复改数据）。
-- 覆盖评审项：P1-1、P2-3、P3（全部清理项）；P1-2 的向量化在 14 单独执行；
--            二轮评审的 R1（函数出参补 purine_level）、R2（50–64 岁女性铁参考并回单行取 12）。
-- 执行方式：psql -d diet_agent -f 12_数据库整改_v1.2_to_v1.2r1.sql
--

\set ON_ERROR_STOP on
\pset pager off

-- ---------------------------------------------------------------------------
-- 0. 前置校验：确认目标库确实是 v1.2 库，避免误执行到别的库
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF to_regclass('app.profile') IS NULL
       OR to_regclass('core.ingredient') IS NULL
       OR to_regclass('knowledge.knowledge_doc') IS NULL THEN
        RAISE EXCEPTION '目标库不是 diet_agent v1.2：缺少 app.profile / core.ingredient / knowledge.knowledge_doc';
    END IF;
END
$$;


-- ---------------------------------------------------------------------------
-- 1. P1-1：profile.conditions 采用 jsonb（定调已确认），并锁定读写契约
--    现状：v1.2 已交付 jsonb，但库层没有任何形状约束，后端照 text[] 写会静默错配。
--    整改：加形状校验函数 + CHECK 约束（NOT VALID：新写入强制，存量待核）；
--          补一份"新字段优先、旧字段兜底"的读取视图，明确旧字段只读保留。
--    conditions 形状（与 app.preview_daily_condition_nutrient_rule 的取值路径一致）：
--      {"<condition_id>": {"status": "confirmed|suspected|unknown",
--                          "<profile_override_key>": 1200, ...}, ...}
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION app.is_condition_map_valid(p_conditions jsonb)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
    SELECT CASE
        WHEN p_conditions IS NULL THEN false
        WHEN jsonb_typeof(p_conditions) <> 'object' THEN false
        ELSE NOT EXISTS (
            SELECT 1
            FROM jsonb_each(p_conditions) AS e(condition_id, detail)
            WHERE jsonb_typeof(e.detail) <> 'object'
               OR (
                    e.detail ? 'status'
                    AND (e.detail ->> 'status') <> ALL (ARRAY['confirmed', 'suspected', 'unknown'])
               )
        )
    END
$$;

COMMENT ON FUNCTION app.is_condition_map_valid(jsonb) IS
    '校验 profile.conditions 形状：必须是以 condition_id 为键的对象，每个值必须是对象，status 只允许 confirmed/suspected/unknown。';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'app.profile'::regclass
          AND conname = 'profile_conditions_contract_check'
    ) THEN
        ALTER TABLE app.profile
            ADD CONSTRAINT profile_conditions_contract_check
            CHECK (app.is_condition_map_valid(conditions)) NOT VALID;
    END IF;
END
$$;

COMMENT ON CONSTRAINT profile_conditions_contract_check ON app.profile IS
    'conditions 形状契约；以 NOT VALID 加入，新写入立即校验，存量数据由 04 验收脚本报告。';

-- 旧字段定调：只读保留（不删除），新代码一律经 v_profile_effective 读取
COMMENT ON COLUMN app.profile.activity_level IS 'v1.1兼容字段：只读保留，不写入新业务数据；新接口用 goal_code 与 target_calories。';
COMMENT ON COLUMN app.profile.extras IS 'v1.1兼容字段：只读保留；新业务字段请使用独立列，不要继续向 extras 塞数据。';
COMMENT ON COLUMN app.profile.taboos IS 'v1.1兼容字段：只读保留；新接口的宗教与伦理禁忌使用 religious_ethical。';

CREATE OR REPLACE VIEW app.v_profile_effective AS
SELECT
    p.profile_id,
    p.user_id,
    p.name,
    p.avatar,
    COALESCE(p.gender, p.sex)                                     AS gender,
    COALESCE(p.goal_code, p.goal)                                 AS goal_code,
    p.birth_date,
    p.age,
    app.age_in_months(p.birth_date, CURRENT_DATE)                  AS age_months,
    p.height_cm,
    p.weight_kg,
    p.activity_level,
    p.target_calories,
    p.allergies,
    p.taboos,
    p.religious_ethical,
    p.cooking_equipment,
    p.conditions,
    p.extras,
    p.profile_version,
    p.created_at,
    p.updated_at,
    (p.gender IS NULL AND p.sex IS NOT NULL)                       AS gender_from_legacy,
    (p.goal_code IS NULL AND p.goal IS NOT NULL)                    AS goal_code_from_legacy
FROM app.profile p;

COMMENT ON VIEW app.v_profile_effective IS
    '用户档案唯一读取入口：新字段优先、v1.1 旧字段兜底，并用 *_from_legacy 标记兜底来源；写入仍只写新字段。';


-- ---------------------------------------------------------------------------
-- 2. P2-3：食材检索视图/函数补齐 data_quality / source_note / iodine_ug / sfa_g
--    视图加 4 列（data_quality、source_note、iodine_ug、sfa_g）
--    函数出参加 6 列（上述 4 列 + purine_level + has_missing_macro）
--    取值口径：
--      data_quality  ← core.ingredient.data_quality（正式列，不套 v1.1 脚本推导）
--      source_note   ← ingredient.source_row->>'source_note' 优先，回退 core.data_source.notes
--      iodine_ug     ← micro_nutrients->>'iodine_ug' 优先，回退 source_row->>'iodine_ug'
--      sfa_g         ← core.ingredient.sfa_g（缺失保持 NULL，不得用 fat_g 替代）
--    R1（二轮评审）：视图早就有 purine_level，函数出参漏了，后端走函数搜食材拿不到嘌呤等级，
--    这里补上，位置放在 allergen_status 之后（与视图列顺序一致）。
--    出参顺序说明：food_id, name, aliases, category, state, energy_kcal, protein_g, fat_g,
--                  carbohydrate_g, allergens, allergen_status, purine_level, match_type,
--                  data_quality, source_note, iodine_ug, sfa_g, has_missing_macro（共 18 个）。
--    出参变化无法用 CREATE OR REPLACE 覆盖，必须先删后建。
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW app.v_ingredient_search AS
SELECT
    i.food_id,
    i.name,
    i.aliases,
    i.category,
    i.state,
    i.edible_portion_pct,
    i.energy_kcal,
    i.protein_g,
    i.fat_g,
    i.carbohydrate_g,
    i.fiber_g,
    i.sodium_mg,
    i.potassium_mg,
    i.calcium_mg,
    i.magnesium_mg,
    i.allergens,
    i.allergen_status,
    i.purine_level,
    i.source_url,
    ((i.protein_g IS NULL) OR (i.fat_g IS NULL) OR (i.carbohydrate_g IS NULL)) AS has_missing_macro,
    concat_ws(' ', i.name, array_to_string(i.aliases, ' '), i.category, i.state) AS search_text,
    i.data_quality,
    COALESCE(
        nullif(i.source_row ->> 'source_note', ''),
        ds.notes
    ) AS source_note,
    CASE
        WHEN (i.micro_nutrients ->> 'iodine_ug') ~ '^-?[0-9]+([.][0-9]+)?$'
            THEN (i.micro_nutrients ->> 'iodine_ug')::numeric
        WHEN (i.source_row ->> 'iodine_ug') ~ '^-?[0-9]+([.][0-9]+)?$'
            THEN (i.source_row ->> 'iodine_ug')::numeric
        ELSE NULL
    END AS iodine_ug,
    i.sfa_g
FROM core.ingredient i
LEFT JOIN core.data_source ds ON ds.source_id = i.source_id
WHERE NOT i.is_deleted;

COMMENT ON VIEW app.v_ingredient_search IS
    '面向应用的食材搜索视图；保留 NULL，不把缺失营养值显示为 0。v1.2r1 增补 data_quality / source_note / iodine_ug / sfa_g。';

DROP FUNCTION IF EXISTS app.search_ingredients(text, integer);

CREATE FUNCTION app.search_ingredients(p_query text, p_limit integer DEFAULT 20)
RETURNS TABLE(
    food_id text,
    name text,
    aliases text[],
    category text,
    state text,
    energy_kcal numeric,
    protein_g numeric,
    fat_g numeric,
    carbohydrate_g numeric,
    allergens text[],
    allergen_status text,
    purine_level text,
    match_type text,
    data_quality text,
    source_note text,
    iodine_ug numeric,
    sfa_g numeric,
    has_missing_macro boolean
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        v.food_id,
        v.name,
        v.aliases,
        v.category,
        v.state,
        v.energy_kcal,
        v.protein_g,
        v.fat_g,
        v.carbohydrate_g,
        v.allergens,
        v.allergen_status,
        v.purine_level,
        CASE
            WHEN v.name = btrim(p_query) THEN 'name_exact'
            WHEN btrim(p_query) = ANY (v.aliases) THEN 'alias_exact'
            WHEN v.name ILIKE btrim(p_query) || '%' THEN 'name_prefix'
            WHEN EXISTS (
                SELECT 1 FROM unnest(v.aliases) AS alias_name
                WHERE alias_name ILIKE btrim(p_query) || '%'
            ) THEN 'alias_prefix'
            ELSE 'contains'
        END AS match_type,
        v.data_quality,
        v.source_note,
        v.iodine_ug,
        v.sfa_g,
        v.has_missing_macro
    FROM app.v_ingredient_search v
    WHERE nullif(btrim(p_query), '') IS NOT NULL
      AND (
          v.name ILIKE '%' || btrim(p_query) || '%'
          OR EXISTS (
              SELECT 1 FROM unnest(v.aliases) AS alias_name
              WHERE alias_name ILIKE '%' || btrim(p_query) || '%'
          )
      )
    ORDER BY
        CASE
            WHEN v.name = btrim(p_query) THEN 0
            WHEN btrim(p_query) = ANY (v.aliases) THEN 1
            WHEN v.name ILIKE btrim(p_query) || '%' THEN 2
            ELSE 3
        END,
        v.name,
        v.food_id
    LIMIT least(greatest(coalesce(p_limit, 20), 1), 100)
$$;

COMMENT ON FUNCTION app.search_ingredients(text, integer) IS
    '按名称和别名进行精确、前缀和包含搜索；不依赖中文分词扩展。出参 18 个：在基础营养之后补 purine_level（R1）、data_quality / source_note / iodine_ug / sfa_g / has_missing_macro（P2-3）。';


-- ---------------------------------------------------------------------------
-- 2b. R2（二轮评审）：50–64 岁女性铁参考并回单行，取 12
--     现状：core.nutrient_reference 里"女 / 50-64"这一格按月经状态拆成两行
--           （无月经 10、有月经 12）。app.match_nutrient_reference 的过滤条件是
--           "nr.menstrual_status = '' OR 请求未给月经状态 OR 相等"，
--           于是档案没采月经状态时两行同时命中 → needs_clarification=true，
--           每次算铁都追问一次，实际把营养计算卡住。
--     整改：并回单行，menstrual_status 置空（通用行），value 取 12（有月经值，偏保守的那一侧）。
--           18-49 岁女性仍是单行 18，65 岁以上仍是单行 10，不受影响（只改 50-64 这一格）。
--     幂等：删掉的只是"无月经"行；重复执行时该行已不存在，UPDATE 也只会把值再写一遍 12。
--     源数据同步：rni_reference.json 里 iron 的 values 仍是两行，库内已并回单行，
--           源文件待数据岗位下次整理时同步（本脚本只改库，不动源数据文件）。
-- ---------------------------------------------------------------------------
-- R2 数据修订：合并 50–64 岁女性铁参考（开始）
DO $$
DECLARE
    v_total integer;
    v_no_menstruation integer;
    v_menstruation integer;
    v_generic integer;
    v_deleted integer := 0;
    v_updated integer := 0;
    v_after integer;
BEGIN
    SELECT count(*),
           count(*) FILTER (WHERE menstrual_status = '无月经'),
           count(*) FILTER (WHERE menstrual_status = '有月经'),
           count(*) FILTER (WHERE menstrual_status = '')
      INTO v_total, v_no_menstruation, v_menstruation, v_generic
      FROM core.nutrient_reference
     WHERE nutrient_id = 'iron'
       AND sex = 'female'
       AND age_group = '50-64'
       AND life_stage = '普通';

    IF v_total = 0 THEN
        RAISE NOTICE '未找到"女 / 50-64 / 普通"的铁参考行，跳过 R2（若目标库刚恢复，请确认 nutrient_reference 已导入）';
        RETURN;
    END IF;

    -- 只有"两行拆分"的形态才需要合并；单行已是通用行时直接跳过，避免误删
    IF v_no_menstruation = 1 AND v_menstruation >= 1 THEN
        DELETE FROM core.nutrient_reference
         WHERE nutrient_id = 'iron'
           AND sex = 'female'
           AND age_group = '50-64'
           AND life_stage = '普通'
           AND menstrual_status = '无月经';
        GET DIAGNOSTICS v_deleted = ROW_COUNT;
    END IF;

    IF v_total = 2 AND v_generic = 0 THEN
        UPDATE core.nutrient_reference
           SET menstrual_status = '',
               value = 12,
               note = 'R2：50–64 岁女性并回单行取 12（原按月经状态拆为 无月经 10 / 有月经 12，'
                      || '未采月经状态时两行同时命中会导致反复追问，故取保守侧 12）',
               source_row = COALESCE(source_row, '{}'::jsonb)
                            || jsonb_build_object(
                                   'review_decision', 'R2-merge-50-64-female-iron',
                                   'merged_from', jsonb_build_array(
                                       jsonb_build_object('menstrual_status', '有月经', 'value', 12),
                                       jsonb_build_object('menstrual_status', '无月经', 'value', 10)
                                   ),
                                   'merged_value', 12
                               )
         WHERE nutrient_id = 'iron'
           AND sex = 'female'
           AND age_group = '50-64'
           AND life_stage = '普通'
           AND menstrual_status = '有月经';
        GET DIAGNOSTICS v_updated = ROW_COUNT;
    END IF;

    SELECT count(*) INTO v_after
      FROM core.nutrient_reference
     WHERE nutrient_id = 'iron'
       AND sex = 'female'
       AND age_group = '50-64'
       AND life_stage = '普通';

    IF v_after <> 1 THEN
        RAISE EXCEPTION 'R2 未收敛：合并后"女 / 50-64 / 普通"的铁参考应为 1 行，实际 % 行', v_after;
    END IF;

    RAISE NOTICE 'R2 完成：删除 无月经 行 % 条，改写 有月经 行为通用行 % 条，当前该格 % 行', v_deleted, v_updated, v_after;
END
$$;
-- R2 数据修订：合并 50–64 岁女性铁参考（结束）


-- ---------------------------------------------------------------------------
-- 3. P3 清理项
-- ---------------------------------------------------------------------------

-- 3.1 测试视图（硬编码虚构数据）不留在生产库；分支验收改由 04 验收脚本在事务里跑真实规则
DROP VIEW IF EXISTS app.v_condition_rule_branch_acceptance;

-- 3.2 staging 暂存层移出生产库。原始导入快照仍完整保存在
--     core.ingredient.source_row / core.dish.source_row（逐行 jsonb），可追溯性不受影响。
DROP SCHEMA IF EXISTS staging CASCADE;

-- 3.3 3 条 legacy 方案与 1 条迁移报告：确认有意保留
--     用途：v1.1→v1.2 兼容性回归样本，且 04 验收脚本以 count(data_version='legacy-v1.1') >= 3 断言其未被误删。
--     清理口径：只标记不删除。
UPDATE app.meal_plan
   SET sources = CASE
       WHEN jsonb_typeof(COALESCE(sources, '{}'::jsonb)) = 'object'
        AND NOT (COALESCE(sources, '{}'::jsonb) ? 'retention')
       THEN COALESCE(sources, '{}'::jsonb) || '{"retention": "legacy-regression-sample"}'::jsonb
       ELSE sources
   END
 WHERE data_version = 'legacy-v1.1';


-- ---------------------------------------------------------------------------
-- 4. 迁移登记与权限
-- ---------------------------------------------------------------------------
INSERT INTO audit.schema_migration (migration_id, description)
SELECT '2026-11-13-review-r1',
       '按 v1.2 评审意见整改：conditions 契约化（P1-1）、食材检索补 5 字段（P2-3）、清理 staging 与测试视图（P3）'
WHERE NOT EXISTS (
    SELECT 1 FROM audit.schema_migration WHERE migration_id = '2026-11-13-review-r1'
);

INSERT INTO audit.schema_migration (migration_id, description)
SELECT '2026-11-13-review-r1b',
       '二轮评审 R1/R2：search_ingredients 补 purine_level（R1）、50–64 岁女性铁参考并回单行取 12（R2）'
WHERE NOT EXISTS (
    SELECT 1 FROM audit.schema_migration WHERE migration_id = '2026-11-13-review-r1b'
);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'diet_app') THEN
        GRANT SELECT ON app.v_profile_effective TO diet_app;
        GRANT SELECT ON app.v_ingredient_search TO diet_app;
        GRANT EXECUTE ON FUNCTION app.search_ingredients(text, integer) TO diet_app;
        GRANT EXECUTE ON FUNCTION app.is_condition_map_valid(jsonb) TO diet_app;
    END IF;
END
$$;

-- ---------------------------------------------------------------------------
-- 5. 自检输出（供执行者肉眼确认）
-- ---------------------------------------------------------------------------
SELECT 'r1 migrated' AS check_item,
       count(*)::text AS result
  FROM audit.schema_migration
 WHERE migration_id = '2026-11-13-review-r1'
UNION ALL
SELECT 'r1b migrated', count(*)::text
  FROM audit.schema_migration
 WHERE migration_id = '2026-11-13-review-r1b'
UNION ALL
SELECT 'staging_gone', (to_regclass('staging.food_raw') IS NULL)::text
UNION ALL
SELECT 'test_view_gone', (to_regclass('app.v_condition_rule_branch_acceptance') IS NULL)::text
UNION ALL
SELECT 'ingredient_view_columns', count(*)::text
  FROM information_schema.columns
 WHERE table_schema = 'app' AND table_name = 'v_ingredient_search'
UNION ALL
SELECT 'search_func_out_columns', count(*)::text
  FROM information_schema.parameters
 WHERE specific_schema = 'app' AND specific_name LIKE 'search_ingredients%'
   AND parameter_mode = 'OUT'
UNION ALL
SELECT 'search_func_has_purine_level',
       (count(*) > 0)::text
  FROM information_schema.parameters
 WHERE specific_schema = 'app' AND specific_name LIKE 'search_ingredients%'
   AND parameter_mode = 'OUT'
   AND parameter_name = 'purine_level'
UNION ALL
SELECT 'iron_female_50_64_rows',
       (SELECT count(*) FROM core.nutrient_reference
         WHERE nutrient_id = 'iron' AND sex = 'female'
           AND age_group = '50-64' AND life_stage = '普通')::text
ORDER BY check_item;
