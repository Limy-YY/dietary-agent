--
-- 43_审核激活验收_v1.2r4.sql
-- 用途：41（反向营养激活）与 42（疾病规则口径审核）执行后的验收。只读，不改数据。
--
-- 判定口径：
--   · 反向营养：19 条全部 approved+is_active、字段齐全、8/11 分级、7 种关键微量覆盖、
--     多症状输入（"乏力 掉发"）能同时命中两条映射（对应 IMP-038 的实测场景）。
--   · 疾病规则：9 条 approved、7 条生效、钠阈值唯一、4 病种全覆盖、非数值规则不带阈值语义。
--   · 非数值口径自证：对已确诊痛风用户评估 GOUT-PATTERN-LOW-PURINE，生产函数应返回 0 行
--     （rule_kind 不在 nutrient_limit/target 内），证明"模式偏好不会被误判成达标/超标"。
--
-- 前置：01 备份 → 12 → 03 → 18 → 38 → 39 → 14 → 19 → 20 → 21 → 41 → 42。
-- 用法：psql -d diet_agent -v ON_ERROR_STOP=1 -f 43_审核激活验收_v1.2r4.sql
--

\set ON_ERROR_STOP on
\pset pager off

DO $$
DECLARE
    v_mig_symptom integer;
    v_mig_rule integer;
    v_symptom_total integer;
    v_symptom_active integer;
    v_symptom_moderate integer;
    v_symptom_low integer;
    v_symptom_bad integer;
    v_key_nutrients integer;
    v_pending_left integer;
    v_multi_hit integer;
    v_rules integer;
    v_rules_approved integer;
    v_rules_active integer;
    v_active_sodium integer;
    v_conditions integer;
    v_production integer;
    v_bad_non_numeric integer;
    v_missing_source integer;
    v_missing_review integer;
BEGIN
    SELECT count(*) INTO v_mig_symptom FROM audit.schema_migration
     WHERE migration_id = '2026-11-19-reverse-nutrition-activation';
    SELECT count(*) INTO v_mig_rule FROM audit.schema_migration
     WHERE migration_id = '2026-11-19-condition-rule-review';

    IF v_mig_symptom <> 1 THEN
        RAISE EXCEPTION '未找到反向营养激活迁移记录：请先执行 41_反向营养映射审核激活_v1.2r4.sql';
    END IF;
    IF v_mig_rule <> 1 THEN
        RAISE EXCEPTION '未找到疾病规则审核迁移记录：请先执行 42_疾病规则口径审核_v1.2r4.sql';
    END IF;

    -- 一、反向营养
    SELECT count(*), count(*) FILTER (WHERE is_active),
           count(*) FILTER (WHERE evidence_level = 'moderate'),
           count(*) FILTER (WHERE evidence_level = 'low'),
           count(*) FILTER (WHERE review_status <> 'approved' OR NOT is_reviewed
                               OR reviewer IS NULL OR reviewed_at IS NULL OR source_id IS NULL)
      INTO v_symptom_total, v_symptom_active, v_symptom_moderate, v_symptom_low, v_symptom_bad
      FROM core.symptom_nutrient_map
     WHERE (symptom, nutrient_id) IN (
         VALUES
         ('容易疲劳','iron'), ('注意力不集中','iron'),
         ('夜间视物困难','vitamin_a'), ('眼睛干涩','vitamin_a'),
         ('牙龈出血','vitamin_c'), ('伤口愈合慢','vitamin_c'), ('容易出现瘀斑','vitamin_c'),
         ('嘴角容易破','vitamin_b2'), ('嘴唇肿胀开裂','vitamin_b2'), ('舌头肿痛','vitamin_b2'),
         ('味觉或嗅觉减退','zinc'), ('骨量偏低','calcium'), ('食欲下降','vitamin_b1'),
         ('掉发','iron'), ('便秘','dietary_fiber'), ('失眠','magnesium'),
         ('腿抽筋','calcium'), ('口腔溃疡反复','vitamin_b2'), ('皮肤干燥','vitamin_a')
     );

    SELECT count(DISTINCT nutrient_id) INTO v_key_nutrients
      FROM core.symptom_nutrient_map
     WHERE nutrient_id IN ('calcium','iron','zinc','vitamin_a','vitamin_b1','vitamin_b2','vitamin_c')
       AND is_active;

    SELECT count(*) INTO v_pending_left
      FROM core.symptom_nutrient_map
     WHERE review_status = 'pending'
       AND (symptom, nutrient_id) IN (
           VALUES ('容易疲劳','iron'), ('身体无力','iron'), ('容易骨折','calcium'),
                  ('记忆力下降','vitamin_b1'), ('舌头肿痛','vitamin_b6'), ('舌头肿痛','vitamin_b2')
       );

    -- 与后端 _search_symptom_map 相同的子串命中语义：症状或别名出现在输入文本里即命中
    SELECT count(*) INTO v_multi_hit
      FROM core.symptom_nutrient_map m
     WHERE m.is_active
       AND EXISTS (
           SELECT 1 FROM unnest(array[m.symptom] || m.aliases) AS t(term)
            WHERE coalesce(t.term, '') <> ''
              AND position(t.term in '乏力 掉发') > 0
       );

    IF v_symptom_total <> 19 THEN
        RAISE EXCEPTION '本批反向营养映射应为19条，实际%条', v_symptom_total;
    END IF;
    IF v_symptom_active <> 19 THEN
        RAISE EXCEPTION '应19条全部启用，实际%条', v_symptom_active;
    END IF;
    IF v_symptom_moderate <> 8 OR v_symptom_low <> 11 THEN
        RAISE EXCEPTION '证据分级应为 moderate 8 / low 11，实际 % / %', v_symptom_moderate, v_symptom_low;
    END IF;
    IF v_symptom_bad <> 0 THEN
        RAISE EXCEPTION '有%条已启用映射缺审核字段或来源', v_symptom_bad;
    END IF;
    IF v_key_nutrients <> 7 THEN
        RAISE EXCEPTION '已启用映射覆盖关键微量%种，应7种', v_key_nutrients;
    END IF;
    IF v_pending_left <> 0 THEN
        RAISE EXCEPTION '本批仍有%条待审核残留（旧稿未清理干净）', v_pending_left;
    END IF;
    IF v_multi_hit < 2 THEN
        RAISE EXCEPTION '输入「乏力 掉发」只命中%条映射，应至少2条（乏力→铁、掉发→铁）', v_multi_hit;
    END IF;

    -- 二、疾病规则
    SELECT count(*),
           count(*) FILTER (WHERE review_status = 'approved'),
           count(*) FILTER (WHERE is_active)
      INTO v_rules, v_rules_approved, v_rules_active
      FROM core.condition_nutrient_rule
     WHERE rule_id IN ('HTN-SODIUM-WHO-NHC-2000', 'HTN-SODIUM-DASH-2300', 'HTN-SODIUM-DASH-1500',
                       'HTN-PATTERN-DASH', 'DM-PATTERN-LOW-GI', 'DM-ADDED-SUGAR-GATE',
                       'GOUT-PATTERN-LOW-PURINE', 'GOUT-HIGH-PURINE-GATE', 'HLP-PATTERN-LOW-SATFAT');

    SELECT count(*) INTO v_active_sodium
      FROM core.condition_nutrient_rule
     WHERE is_active AND nutrient_id = 'sodium'
       AND rule_kind IN ('nutrient_limit', 'nutrient_target');

    SELECT count(DISTINCT condition_id) INTO v_conditions
      FROM core.condition_nutrient_rule
     WHERE is_active AND condition_id IN ('hypertension', 'diabetes', 'gout', 'hyperlipidemia');

    SELECT count(*) INTO v_production FROM app.v_production_condition_rules;

    SELECT count(*) INTO v_bad_non_numeric
      FROM core.condition_nutrient_rule
     WHERE is_active
       AND rule_kind IN ('pattern_preference', 'review_gate')
       AND coalesce(evaluator ->> 'numeric_evaluation', 'true') <> 'false';

    SELECT count(*) INTO v_missing_source
      FROM core.condition_nutrient_rule r
     WHERE r.is_active
       AND NOT EXISTS (SELECT 1 FROM core.condition_rule_source rs WHERE rs.rule_id = r.rule_id);

    SELECT count(*) INTO v_missing_review
      FROM core.condition_nutrient_rule r
     WHERE r.is_active
       AND NOT EXISTS (SELECT 1 FROM audit.condition_rule_review rv
                        WHERE rv.rule_id = r.rule_id AND rv.decision = 'approved');

    IF v_rules <> 9 THEN
        RAISE EXCEPTION '本轮疾病规则应为9条，实际%条', v_rules;
    END IF;
    IF v_rules_approved <> 9 THEN
        RAISE EXCEPTION '应9条全部 approved，实际%条', v_rules_approved;
    END IF;
    IF v_rules_active <> 7 THEN
        RAISE EXCEPTION '生效规则应7条，实际%条', v_rules_active;
    END IF;
    IF v_active_sodium <> 1 THEN
        RAISE EXCEPTION '生效钠阈值规则应唯一，实际%条（多目标并行会自相矛盾）', v_active_sodium;
    END IF;
    IF v_conditions <> 4 THEN
        RAISE EXCEPTION '生效规则应覆盖4个病种，实际%个', v_conditions;
    END IF;
    IF v_production <> 7 THEN
        RAISE EXCEPTION 'v_production_condition_rules 应为7条，实际%条', v_production;
    END IF;
    IF v_bad_non_numeric <> 0 THEN
        RAISE EXCEPTION '有%条生效的非数值规则未声明 numeric_evaluation=false', v_bad_non_numeric;
    END IF;
    IF v_missing_source <> 0 THEN
        RAISE EXCEPTION '有%条生效规则缺来源', v_missing_source;
    END IF;
    IF v_missing_review <> 0 THEN
        RAISE EXCEPTION '有%条生效规则缺审批记录', v_missing_review;
    END IF;

    RAISE NOTICE '43号验收通过：反向营养19条已启用（8/11），疾病规则9条已审核、7条生效、钠目标唯一、4病种覆盖';
END $$;

-- ---------------------------------------------------------------------------
-- 三、非数值口径自证：模式偏好规则不得被评估成达标/超标
-- ---------------------------------------------------------------------------
BEGIN;

INSERT INTO app.profile (user_id, name, conditions)
VALUES ('TEST-R4-PATTERN-PROOF', '口径自证-已确诊痛风',
        '{"gout": {"status": "confirmed"}}'::jsonb);

DO $$
DECLARE
    v_pattern_rows integer;
    v_sodium_rows integer;
BEGIN
    -- 模式偏好规则：生产函数不评估（rule_kind 过滤），返回 0 行
    SELECT count(*) INTO v_pattern_rows
      FROM app.evaluate_daily_condition_nutrient_rule(
          'TEST-R4-PATTERN-PROOF', DATE '2026-11-19', 'GOUT-PATTERN-LOW-PURINE');

    IF v_pattern_rows <> 0 THEN
        RAISE EXCEPTION '模式偏好规则被生产函数评估了（%行），会误导成数值达标判断', v_pattern_rows;
    END IF;

    -- 对照：已确诊用户 + 已启用钠阈值规则 → 应返回 1 行（当天无摄入 => no_intake_data）
    SELECT count(*) INTO v_sodium_rows
      FROM app.preview_daily_condition_nutrient_rule(
          'TEST-R4-PATTERN-PROOF', DATE '2026-11-19', 'HTN-SODIUM-WHO-NHC-2000');

    IF v_sodium_rows <> 1 THEN
        RAISE EXCEPTION '对照失败：钠阈值规则预览应返回1行，实际%行', v_sodium_rows;
    END IF;
END $$;

ROLLBACK;

-- ---------------------------------------------------------------------------
-- 四、结果摘要
-- ---------------------------------------------------------------------------
SELECT 'reverse_nutrition_total' AS check_item, count(*)::text AS result
  FROM core.symptom_nutrient_map
UNION ALL
SELECT 'reverse_nutrition_active', count(*)::text FROM core.symptom_nutrient_map WHERE is_active
UNION ALL
SELECT 'reverse_nutrition_multi_hit（乏力 掉发）',
       (SELECT count(*)::text FROM core.symptom_nutrient_map m
         WHERE m.is_active AND EXISTS (
             SELECT 1 FROM unnest(array[m.symptom] || m.aliases) AS t(term)
              WHERE coalesce(t.term, '') <> '' AND position(t.term in '乏力 掉发') > 0))
UNION ALL
SELECT 'condition_rules_total', count(*)::text FROM core.condition_nutrient_rule
UNION ALL
SELECT 'condition_rules_active', count(*)::text FROM core.condition_nutrient_rule WHERE is_active
UNION ALL
SELECT 'production_rules', count(*)::text FROM app.v_production_condition_rules
UNION ALL
SELECT 'active_nutrient_limits',
       count(*)::text FROM core.condition_nutrient_rule
        WHERE is_active AND rule_kind IN ('nutrient_limit', 'nutrient_target')
ORDER BY check_item;
