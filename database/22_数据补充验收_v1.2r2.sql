\set ON_ERROR_STOP on
\pset pager off

-- v1.2r4 合并版数据补充验收：铁参考值、纤维、钙、审核修订后的反向营养映射，叠加 v1.2r2 菜式扩充（60 → 120）。
-- 反向营养按阶段验收（v1.2r4 起）：
--   激活前（未跑 41）：13 条待审核、0 条启用、moderate 7 / low 6；
--   激活后（已跑 41）：19 条全部 approved+启用、moderate 8 / low 11。
-- 两个阶段由 audit.schema_migration 里的 41 号迁移记录区分，避免同一套断言在两种状态下互相打架。

DO $$
DECLARE
    v_ingredient_count integer;
    v_dish_count integer;
    v_used_ingredient_count integer;
    v_r1_used integer;
    v_r1_fiber_missing integer;
    v_r1_calcium_missing integer;
    v_pending_fiber_ingredients integer;
    v_dish_nutrition_count integer;
    v_iron_count integer;
    v_iron_value numeric;
    v_iron_status text;
    v_symptom_count integer;
    v_pending_count integer;
    v_active_count integer;
    v_key_nutrient_count integer;
    v_bad_evidence_count integer;
    v_moderate_count integer;
    v_low_count integer;
    v_symptom_review_applied integer;
    v_bad_review_rows integer;
    v_doc_count integer;
BEGIN
    SELECT count(*) INTO v_ingredient_count FROM core.ingredient WHERE NOT is_deleted;
    SELECT count(*) INTO v_dish_count FROM core.dish WHERE NOT is_deleted;

    SELECT count(DISTINCT i.ingredient_id)
      INTO v_used_ingredient_count
      FROM core.dish_ingredient di
      JOIN core.ingredient i ON i.ingredient_id = di.ingredient_id
      JOIN core.dish d ON d.dish_id = di.dish_id
     WHERE NOT d.is_deleted;

    SELECT count(DISTINCT i.ingredient_id),
           count(DISTINCT i.ingredient_id) FILTER (WHERE i.fiber_g IS NULL),
           count(DISTINCT i.ingredient_id) FILTER (WHERE i.calcium_mg IS NULL)
      INTO v_r1_used, v_r1_fiber_missing, v_r1_calcium_missing
      FROM core.dish_ingredient di
      JOIN core.ingredient i ON i.ingredient_id = di.ingredient_id
      JOIN core.dish d ON d.dish_id = di.dish_id
     WHERE NOT d.is_deleted AND d.dish_id < 'DISH-061';

    -- v1.2r2 扩充批次（DISH-061..120）复用食材中仍有 30 种缺纤维，钙已补齐；
    -- 这批菜式的纤维快照留待微量/宏量补录批次处理，不作为本包验收阻塞项。
    SELECT count(DISTINCT i.ingredient_id) FILTER (WHERE i.fiber_g IS NULL)
      INTO v_pending_fiber_ingredients
      FROM core.dish_ingredient di
      JOIN core.ingredient i ON i.ingredient_id = di.ingredient_id
      JOIN core.dish d ON d.dish_id = di.dish_id
     WHERE NOT d.is_deleted;

    SELECT count(*) INTO v_dish_nutrition_count
      FROM core.dish
     WHERE NOT is_deleted
       AND nutrition_snapshot ? 'dish_fiber_g'
       AND nutrition_snapshot ? 'dish_calcium_mg';

    SELECT count(*), min(value), min(menstrual_status)
      INTO v_iron_count, v_iron_value, v_iron_status
      FROM core.nutrient_reference
     WHERE nutrient_id = 'iron'
       AND sex = 'female'
       AND age_group = '50-64'
       AND life_stage = '普通';

    SELECT count(*),
           count(*) FILTER (WHERE review_status = 'pending'),
           count(*) FILTER (WHERE is_active)
      INTO v_symptom_count, v_pending_count, v_active_count
      FROM core.symptom_nutrient_map;

    SELECT count(DISTINCT nutrient_id) INTO v_key_nutrient_count
      FROM core.symptom_nutrient_map
     WHERE nutrient_id IN ('calcium','iron','zinc','vitamin_a','vitamin_b1','vitamin_b2','vitamin_c');

    SELECT count(*) INTO v_bad_evidence_count
      FROM core.symptom_nutrient_map
     WHERE review_status = 'pending'
       AND evidence_level NOT IN ('strong','moderate','low');

    SELECT count(*) FILTER (WHERE evidence_level = 'moderate'),
           count(*) FILTER (WHERE evidence_level = 'low')
      INTO v_moderate_count, v_low_count
      FROM core.symptom_nutrient_map;

    -- v1.2r4 起反向营养有「激活前 / 激活后」两个合法状态，用 41 号的迁移记录区分阶段，
    -- 否则同一套断言会在两种状态下互相打架（41 已跑时 pending 必然为 0）。
    SELECT count(*) INTO v_symptom_review_applied
      FROM audit.schema_migration
     WHERE migration_id = '2026-11-19-reverse-nutrition-activation';

    SELECT count(*) INTO v_bad_review_rows
      FROM core.symptom_nutrient_map
     WHERE is_active
       AND (review_status <> 'approved' OR NOT is_reviewed
            OR reviewer IS NULL OR reviewed_at IS NULL OR source_id IS NULL);

    SELECT count(*) INTO v_doc_count FROM knowledge.knowledge_doc WHERE NOT is_deleted;

    IF v_ingredient_count <> 128 THEN RAISE EXCEPTION '食材应为128种，实际为%种', v_ingredient_count; END IF;
    IF v_dish_count <> 120 THEN RAISE EXCEPTION '菜式应为120道，实际为%道', v_dish_count; END IF;
    IF v_used_ingredient_count <> 88 THEN RAISE EXCEPTION '120道菜应使用88种食材，实际为%种', v_used_ingredient_count; END IF;
    IF v_r1_used <> 57 THEN RAISE EXCEPTION '首批60道菜应使用57种食材，实际为%种', v_r1_used; END IF;
    IF v_r1_fiber_missing <> 0 THEN RAISE EXCEPTION '首批菜式使用食材仍有%种缺纤维', v_r1_fiber_missing; END IF;
    IF v_r1_calcium_missing <> 0 THEN RAISE EXCEPTION '首批菜式使用食材仍有%种缺钙', v_r1_calcium_missing; END IF;
    IF v_dish_nutrition_count <> 60 THEN RAISE EXCEPTION '有纤维和钙汇总的首批菜式应为60道，实际为%道', v_dish_nutrition_count; END IF;
    IF v_iron_count <> 1 OR v_iron_value <> 12 OR COALESCE(v_iron_status, '') <> '' THEN
        RAISE EXCEPTION '铁·女性50-64岁口径不正确：行数%、数值%、状态%', v_iron_count, v_iron_value, v_iron_status;
    END IF;
    IF v_symptom_review_applied = 0 THEN
        -- 阶段一：41 号还没跑，映射应保持 13 条待审核、0 条启用
        IF v_symptom_count <> 13 OR v_pending_count <> 13 OR v_active_count <> 0 THEN
            RAISE EXCEPTION '反向营养映射状态不正确（激活前）：总数%、待审核%、启用%', v_symptom_count, v_pending_count, v_active_count;
        END IF;
        IF v_moderate_count <> 7 OR v_low_count <> 6 THEN
            RAISE EXCEPTION '反向营养证据分级不正确（激活前）：moderate %条、low %条', v_moderate_count, v_low_count;
        END IF;
    ELSE
        -- 阶段二：41 号已跑，13 条审核修订 + 6 条高频症状 = 19 条全部启用
        IF v_symptom_count <> 19 OR v_pending_count <> 0 OR v_active_count <> 19 THEN
            RAISE EXCEPTION '反向营养映射状态不正确（激活后）：总数%、待审核%、启用%', v_symptom_count, v_pending_count, v_active_count;
        END IF;
        IF v_moderate_count <> 8 OR v_low_count <> 11 THEN
            RAISE EXCEPTION '反向营养证据分级不正确（激活后）：moderate %条、low %条', v_moderate_count, v_low_count;
        END IF;
        IF v_bad_review_rows <> 0 THEN
            RAISE EXCEPTION '有%条已启用反向营养映射缺审核字段或来源', v_bad_review_rows;
        END IF;
    END IF;
    IF v_key_nutrient_count <> 7 THEN
        RAISE EXCEPTION '7种关键微量覆盖不完整，实际覆盖%种', v_key_nutrient_count;
    END IF;
    IF v_bad_evidence_count <> 0 THEN
        RAISE EXCEPTION '待审核反向营养映射仍有%条使用非规范 evidence_level', v_bad_evidence_count;
    END IF;
    IF v_doc_count <> 43 THEN RAISE EXCEPTION '知识文档应为43篇，实际为%篇', v_doc_count; END IF;
END $$;

SELECT check_item, result
  FROM (VALUES
        ('ingredients', (SELECT count(*)::text FROM core.ingredient WHERE NOT is_deleted)),
        ('dishes', (SELECT count(*)::text FROM core.dish WHERE NOT is_deleted)),
        ('dish_used_ingredients', (SELECT count(DISTINCT ingredient_id)::text FROM core.dish_ingredient)),
        ('r1_dishes_used_ingredients', (SELECT count(DISTINCT i.ingredient_id)::text FROM core.dish_ingredient di JOIN core.ingredient i ON i.ingredient_id=di.ingredient_id JOIN core.dish d ON d.dish_id=di.dish_id WHERE d.dish_id<'DISH-061')),
        ('pending_fiber_ingredients_r2_batch', (SELECT count(DISTINCT i.ingredient_id)::text FROM core.dish_ingredient di JOIN core.ingredient i ON i.ingredient_id=di.ingredient_id JOIN core.dish d ON d.dish_id=di.dish_id WHERE NOT d.is_deleted AND i.fiber_g IS NULL)),
        ('dishes_with_fiber_calcium', (SELECT count(*)::text FROM core.dish WHERE NOT is_deleted AND nutrition_snapshot ? 'dish_fiber_g' AND nutrition_snapshot ? 'dish_calcium_mg')),
        ('iron_female_50_64_rows', (SELECT count(*)::text FROM core.nutrient_reference WHERE nutrient_id='iron' AND sex='female' AND age_group='50-64' AND life_stage='普通')),
        ('iron_female_50_64_value', (SELECT min(value)::text FROM core.nutrient_reference WHERE nutrient_id='iron' AND sex='female' AND age_group='50-64' AND life_stage='普通')),
        ('symptom_nutrient_rows', (SELECT count(*)::text FROM core.symptom_nutrient_map)),
        ('symptom_review_phase', CASE WHEN EXISTS (
             SELECT 1 FROM audit.schema_migration
              WHERE migration_id = '2026-11-19-reverse-nutrition-activation')
           THEN 'activated' ELSE 'pending' END),
        ('symptom_pending_rows', (SELECT count(*)::text FROM core.symptom_nutrient_map WHERE review_status='pending')),
        ('symptom_active_rows', (SELECT count(*)::text FROM core.symptom_nutrient_map WHERE is_active)),
        ('symptom_moderate_rows', (SELECT count(*)::text FROM core.symptom_nutrient_map WHERE evidence_level='moderate')),
        ('symptom_low_rows', (SELECT count(*)::text FROM core.symptom_nutrient_map WHERE evidence_level='low')),
        ('symptom_key_nutrients', (SELECT count(DISTINCT nutrient_id)::text FROM core.symptom_nutrient_map WHERE nutrient_id IN ('calcium','iron','zinc','vitamin_a','vitamin_b1','vitamin_b2','vitamin_c'))),
        ('knowledge_docs', (SELECT count(*)::text FROM knowledge.knowledge_doc WHERE NOT is_deleted)),
        ('health_conditions', (SELECT count(*)::text FROM core.health_condition))
       ) AS checks(check_item, result)
 ORDER BY check_item;
