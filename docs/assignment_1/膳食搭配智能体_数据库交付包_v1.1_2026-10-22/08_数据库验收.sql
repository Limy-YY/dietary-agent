\set ON_ERROR_STOP on
\pset pager off

DO $acceptance$
DECLARE
    v_failures text[] := ARRAY[]::text[];
    v_count bigint;
BEGIN
    IF current_setting('server_version_num')::integer < 140000 THEN
        v_failures := array_append(v_failures, 'PostgreSQL版本低于14');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM audit.import_batch
        WHERE import_batch_id = 1 AND status = 'promoted'
    ) THEN
        v_failures := array_append(v_failures, '导入批次1不存在或未推广');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM audit.import_batch
        WHERE import_batch_id = 2
          AND dataset_version = '2026-10-22'
          AND original_sha256 = 'ee771cffa97464ab12cc7f947ec5d58effb9832939aa4173fbdbf7d0ffd54008'
          AND status = 'promoted'
    ) THEN
        v_failures := array_append(v_failures, '食材更新批次2不存在、版本不符或未推广');
    END IF;

    SELECT count(*) INTO v_count FROM core.data_source;
    IF v_count <> 132 THEN v_failures := array_append(v_failures, format('data_source=%s，期望132', v_count)); END IF;

    SELECT count(*) INTO v_count FROM core.ingredient;
    IF v_count <> 128 THEN v_failures := array_append(v_failures, format('ingredient=%s，期望128', v_count)); END IF;

    SELECT count(*) INTO v_count
    FROM core.ingredient
    WHERE (micro_nutrients->>'iodine_ug') IS NOT NULL;
    IF v_count <> 128 THEN v_failures := array_append(v_failures, format('有碘值食材=%s，期望128', v_count)); END IF;

    SELECT count(*) INTO v_count
    FROM core.ingredient
    WHERE purine_level IS NOT NULL;
    IF v_count <> 128 THEN v_failures := array_append(v_failures, format('有嘌呤等级食材=%s，期望128', v_count)); END IF;

    SELECT count(*) INTO v_count
    FROM core.ingredient
    WHERE (source_row->>'data_quality') IN ('official', 'approx', 'check')
      AND source_row ? 'source_note'
      AND source_row ? 'source_registry';
    IF v_count <> 128 THEN v_failures := array_append(v_failures, format('有质量与来源记录食材=%s，期望128', v_count)); END IF;

    SELECT count(*) INTO v_count
    FROM core.ingredient
    WHERE source_row->'source_registry'->>'purine_source' IS NOT NULL;
    IF v_count <> 128 THEN v_failures := array_append(v_failures, format('有嘌呤来源食材=%s，期望128', v_count)); END IF;

    SELECT count(*) INTO v_count
    FROM core.ingredient
    WHERE source_row->'source_registry'->>'iodine_source' IS NOT NULL;
    IF v_count <> 126 THEN v_failures := array_append(v_failures, format('有碘来源名称食材=%s，期望126', v_count)); END IF;

    SELECT count(*) INTO v_count
    FROM core.ingredient
    WHERE food_id = 'CN-1506'
      AND allergens = ARRAY[]::text[]
      AND allergen_status = '确认不含';
    IF v_count <> 1 THEN v_failures := array_append(v_failures, '椰子油过敏原修正未生效'); END IF;

    SELECT count(*) INTO v_count FROM core.food_id_mapping;
    IF v_count <> 32 THEN v_failures := array_append(v_failures, format('food_id_mapping=%s，期望32', v_count)); END IF;

    SELECT count(*) INTO v_count FROM core.cooking_rule;
    IF v_count <> 16 THEN v_failures := array_append(v_failures, format('cooking_rule=%s，期望16', v_count)); END IF;

    SELECT count(*) INTO v_count FROM core.nutrient;
    IF v_count <> 26 THEN v_failures := array_append(v_failures, format('nutrient=%s，期望26', v_count)); END IF;

    SELECT count(*) INTO v_count FROM core.nutrient_reference;
    IF v_count <> 448 THEN v_failures := array_append(v_failures, format('nutrient_reference=%s，期望448', v_count)); END IF;

    SELECT count(*) INTO v_count FROM core.dish;
    IF v_count <> 30 THEN v_failures := array_append(v_failures, format('dish=%s，期望30', v_count)); END IF;

    SELECT count(*) INTO v_count FROM core.dish_ingredient;
    IF v_count <> 127 THEN v_failures := array_append(v_failures, format('dish_ingredient=%s，期望127', v_count)); END IF;

    SELECT count(*) INTO v_count FROM core.dietary_rule_set;
    IF v_count <> 1 THEN v_failures := array_append(v_failures, format('dietary_rule_set=%s，期望1', v_count)); END IF;

    SELECT count(DISTINCT nutrient_id) INTO v_count FROM core.nutrient_reference;
    IF v_count <> 18 THEN v_failures := array_append(v_failures, format('RNI营养素数=%s，期望18', v_count)); END IF;

    SELECT count(*) INTO v_count
    FROM core.dietary_rule_set r
    WHERE jsonb_array_length(r.payload->'chronic_condition_rules') = 5
      AND (SELECT sum(jsonb_array_length(x->'rules'))
           FROM jsonb_array_elements(r.payload->'chronic_condition_rules') x) = 16
      AND jsonb_array_length(r.payload->'food_allergy_rules'->'rules') = 10
      AND jsonb_array_length(r.payload->'references') = 8;
    IF v_count <> 1 THEN
        v_failures := array_append(v_failures, '禁忌规则内容不完整，期望5组慢病/16条慢病规则/10条过敏规则/8个来源');
    END IF;

    SELECT count(*) INTO v_count FROM knowledge.nutrient_knowledge;
    IF v_count <> 26 THEN v_failures := array_append(v_failures, format('nutrient_knowledge=%s，期望26', v_count)); END IF;

    SELECT count(*) INTO v_count FROM knowledge.knowledge_doc;
    IF v_count <> 26 THEN v_failures := array_append(v_failures, format('knowledge_doc=%s，期望26', v_count)); END IF;

    SELECT count(*) INTO v_count
    FROM audit.import_issue
    WHERE severity IN ('P0', 'P1') AND resolved_at IS NULL;
    IF v_count <> 0 THEN v_failures := array_append(v_failures, format('未解决P0/P1=%s，期望0', v_count)); END IF;

    SELECT count(*) INTO v_count
    FROM audit.import_issue
    WHERE severity = 'P2' AND resolved_at IS NULL;
    IF v_count <> 4 THEN v_failures := array_append(v_failures, format('未解决P2=%s，期望4', v_count)); END IF;

    SELECT
        (SELECT count(*) FROM app.profile)
      + (SELECT count(*) FROM app.meal_plan)
      + (SELECT count(*) FROM app.nutrition_result)
      + (SELECT count(*) FROM app.weekly_nutrition_report)
      + (SELECT count(*) FROM app.conversation)
      + (SELECT count(*) FROM app.message)
    INTO v_count;
    IF v_count <> 0 THEN v_failures := array_append(v_failures, format('业务表存在%s行，交付应为空', v_count)); END IF;

    SELECT count(*) INTO v_count
    FROM core.dietary_rule_set WHERE is_active;
    IF v_count <> 0 THEN v_failures := array_append(v_failures, '原始待审核规则集意外启用'); END IF;

    SELECT count(*) INTO v_count
    FROM core.condition_nutrient_rule WHERE is_active OR review_status = 'approved';
    IF v_count <> 0 THEN v_failures := array_append(v_failures, '候选疾病规则意外获批或启用'); END IF;

    IF NOT EXISTS (
        SELECT 1 FROM app.search_ingredients('西红柿', 5)
        WHERE food_id = 'CN-405' AND match_type = 'alias_exact'
    ) THEN
        v_failures := array_append(v_failures, '食材别名搜索验收失败');
    END IF;

    IF cardinality(v_failures) > 0 THEN
        RAISE EXCEPTION 'DATABASE DELIVERY REJECTED: %', array_to_string(v_failures, '; ');
    END IF;
END
$acceptance$;

SELECT 'DATABASE DELIVERY ACCEPTED' AS result;

SELECT * FROM (
    VALUES
      ('core.data_source',             (SELECT count(*) FROM core.data_source)),
      ('core.ingredient',              (SELECT count(*) FROM core.ingredient)),
      ('core.food_id_mapping',         (SELECT count(*) FROM core.food_id_mapping)),
      ('core.cooking_rule',            (SELECT count(*) FROM core.cooking_rule)),
      ('core.nutrient',                (SELECT count(*) FROM core.nutrient)),
      ('core.nutrient_reference',      (SELECT count(*) FROM core.nutrient_reference)),
      ('core.dish',                    (SELECT count(*) FROM core.dish)),
      ('core.dish_ingredient',         (SELECT count(*) FROM core.dish_ingredient)),
      ('core.dietary_rule_set',        (SELECT count(*) FROM core.dietary_rule_set)),
      ('knowledge.nutrient_knowledge', (SELECT count(*) FROM knowledge.nutrient_knowledge)),
      ('knowledge.knowledge_doc',      (SELECT count(*) FROM knowledge.knowledge_doc))
) AS counts(dataset, row_count)
ORDER BY dataset;
