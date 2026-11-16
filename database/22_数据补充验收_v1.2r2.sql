\set ON_ERROR_STOP on
\pset pager off

-- v1.2r2 数据补充验收：铁参考值、纤维、钙、反向营养映射。

DO $$
DECLARE
    v_ingredient_count integer;
    v_dish_count integer;
    v_used_ingredient_count integer;
    v_used_fiber_missing integer;
    v_used_calcium_missing integer;
    v_dish_nutrition_count integer;
    v_iron_count integer;
    v_iron_value numeric;
    v_iron_status text;
    v_symptom_count integer;
    v_pending_count integer;
    v_active_count integer;
    v_key_nutrient_count integer;
    v_bad_evidence_count integer;
BEGIN
    SELECT count(*) INTO v_ingredient_count FROM core.ingredient WHERE NOT is_deleted;
    SELECT count(*) INTO v_dish_count FROM core.dish WHERE NOT is_deleted;

    SELECT count(DISTINCT i.ingredient_id),
           count(DISTINCT i.ingredient_id) FILTER (WHERE i.fiber_g IS NULL),
           count(DISTINCT i.ingredient_id) FILTER (WHERE i.calcium_mg IS NULL)
      INTO v_used_ingredient_count, v_used_fiber_missing, v_used_calcium_missing
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

    IF v_ingredient_count <> 128 THEN RAISE EXCEPTION '食材应为128种，实际为%种', v_ingredient_count; END IF;
    IF v_dish_count <> 60 THEN RAISE EXCEPTION '菜式应为60道，实际为%道', v_dish_count; END IF;
    IF v_used_ingredient_count <> 57 THEN RAISE EXCEPTION '60道菜应使用57种食材，实际为%种', v_used_ingredient_count; END IF;
    IF v_used_fiber_missing <> 0 THEN RAISE EXCEPTION '菜式使用食材仍有%种缺纤维', v_used_fiber_missing; END IF;
    IF v_used_calcium_missing <> 0 THEN RAISE EXCEPTION '菜式使用食材仍有%种缺钙', v_used_calcium_missing; END IF;
    IF v_dish_nutrition_count <> 60 THEN RAISE EXCEPTION '有纤维和钙汇总的菜式应为60道，实际为%道', v_dish_nutrition_count; END IF;
    IF v_iron_count <> 1 OR v_iron_value <> 12 OR COALESCE(v_iron_status, '') <> '' THEN
        RAISE EXCEPTION '铁·女性50-64岁口径不正确：行数%、数值%、状态%', v_iron_count, v_iron_value, v_iron_status;
    END IF;
    IF v_symptom_count <> 16 OR v_pending_count <> 16 OR v_active_count <> 0 THEN
        RAISE EXCEPTION '反向营养映射状态不正确：总数%、待审核%、启用%', v_symptom_count, v_pending_count, v_active_count;
    END IF;
    IF v_key_nutrient_count <> 7 THEN
        RAISE EXCEPTION '7种关键微量覆盖不完整，实际覆盖%种', v_key_nutrient_count;
    END IF;
    IF v_bad_evidence_count <> 0 THEN
        RAISE EXCEPTION '待审核反向营养映射仍有%条使用非规范 evidence_level', v_bad_evidence_count;
    END IF;
END $$;

SELECT check_item, result
  FROM (VALUES
        ('ingredients', (SELECT count(*)::text FROM core.ingredient WHERE NOT is_deleted)),
        ('dishes', (SELECT count(*)::text FROM core.dish WHERE NOT is_deleted)),
        ('dish_used_ingredients', (SELECT count(DISTINCT ingredient_id)::text FROM core.dish_ingredient)),
        ('dishes_with_fiber_calcium', (SELECT count(*)::text FROM core.dish WHERE NOT is_deleted AND nutrition_snapshot ? 'dish_fiber_g' AND nutrition_snapshot ? 'dish_calcium_mg')),
        ('iron_female_50_64_rows', (SELECT count(*)::text FROM core.nutrient_reference WHERE nutrient_id='iron' AND sex='female' AND age_group='50-64' AND life_stage='普通')),
        ('iron_female_50_64_value', (SELECT min(value)::text FROM core.nutrient_reference WHERE nutrient_id='iron' AND sex='female' AND age_group='50-64' AND life_stage='普通')),
        ('symptom_nutrient_rows', (SELECT count(*)::text FROM core.symptom_nutrient_map)),
        ('symptom_pending_rows', (SELECT count(*)::text FROM core.symptom_nutrient_map WHERE review_status='pending')),
        ('symptom_active_rows', (SELECT count(*)::text FROM core.symptom_nutrient_map WHERE is_active)),
        ('symptom_key_nutrients', (SELECT count(DISTINCT nutrient_id)::text FROM core.symptom_nutrient_map WHERE nutrient_id IN ('calcium','iron','zinc','vitamin_a','vitamin_b1','vitamin_b2','vitamin_c'))),
        ('knowledge_docs', (SELECT count(*)::text FROM knowledge.knowledge_doc WHERE NOT is_deleted)),
        ('health_conditions', (SELECT count(*)::text FROM core.health_condition))
       ) AS checks(check_item, result)
 ORDER BY check_item;
