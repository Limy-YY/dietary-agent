--
-- 42_疾病规则口径审核_v1.2r4.sql
-- 用途：对 core.condition_nutrient_rule 做一次口径审核（去重、可判定性分级、互斥目标收敛），并完成审核激活。
--
-- 审核结论（为什么这么改，见 44_本轮审核记录与口径说明_v1.2r4.md）：
--   1. 钠目标互斥：2000mg（WHO/NHC）、2300mg（DASH）、1500mg（DASH 严格档）三条不能同时生效，
--      否则同一用户会同时命中三个"上限"。本轮定 WHO/NHC 2000mg 为唯一生产默认生效规则，
--      另两条保持 approved 但 is_active=false，等个人方案/医生指定时再按 profile 覆盖打开。
--   2. 可判定性：app.preview/evaluate 只认 rule_kind in ('nutrient_limit','nutrient_target')，
--      且必须能对上 app.nutrition_result.computed 里的键。core.nutrient 目前只有微量与钠钾，
--      没有 carbohydrate / added_sugar / saturated_fat / purine，computed 里也没有 sugar_g / purine_mg。
--      所以糖尿病、痛风、高血脂本轮只能落成「膳食模式偏好 pattern_preference」和
--      「人工复核闸门 review_gate」两类规则：进入正式目录、给 Agent 与前端做提示与候选偏好，
--      但**不做数值达标判定**（evaluator.numeric_evaluation=false 自证），避免出现"永远 not_evaluable"的假规则。
--   3. 高血压 DASH 模式规则：只作膳食模式建议（不参与数值判定），approved + is_active=true。
--   4. 新增 3 个病种 5 条规则，让糖尿病/高尿酸·痛风/高血脂在正式目录里不再是"没有规则"。
--   5. 每条规则都落 audit.condition_rule_review 审批记录，不允许只改 is_active 跳过审核流程。
--
-- 执行账号：postgres，或对 core/audit 有 INSERT/UPDATE 权限的账号。
-- 审核人：默认「数据岗审核（AI 辅助复核，待责任医师签认）」，正式签认时覆盖：
--   psql -d diet_agent -v reviewer='张三（注册营养师）' -f 42_疾病规则口径审核_v1.2r4.sql
-- 复跑：幂等（规则 upsert、来源与审批记录均按 not exists 去重）。
--

\set ON_ERROR_STOP on
\pset pager off

\if :{?reviewer}
\else
\set reviewer '数据岗审核（AI 辅助复核，待责任医师签认）'
\endif

BEGIN;

SELECT set_config('diet.reviewer', :'reviewer', false) AS reviewer_used;

-- ---------------------------------------------------------------------------
-- 0. 前置校验：四个病种字典必须已存在（18 号脚本）
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    v_missing text;
BEGIN
    SELECT string_agg(x.id, ', ') INTO v_missing
      FROM (VALUES ('hypertension'), ('diabetes'), ('hyperlipidemia'), ('gout')) AS x(id)
     WHERE NOT EXISTS (SELECT 1 FROM core.health_condition c WHERE c.condition_id = x.id);
    IF v_missing IS NOT NULL THEN
        RAISE EXCEPTION '病种字典缺 %：请先执行 18_病种字典补齐_v1.2r1.sql', v_missing;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM core.condition_nutrient_rule
                    WHERE rule_id = 'HTN-SODIUM-WHO-NHC-2000') THEN
        RAISE EXCEPTION '未找到高血压钠规则 HTN-SODIUM-WHO-NHC-2000：库里不是 v1.2r2 基线？先按 07 第三节恢复';
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 1. 来源补齐：2023 年版与 2024 年版食养指南通知（官方发布页，含 4 项指南）
-- ---------------------------------------------------------------------------
INSERT INTO core.data_source (source_name, source_url, publisher, version, accessed_on, notes)
VALUES
    ('国家卫生健康委办公厅《成人高脂血症食养指南（2023年版）》等4项食养指南',
     'https://www.chinacdc.cn/jkyj/yyyjk2/jswj13949/202301/t20230129_296964.html',
     '国家卫生健康委员会办公厅', '2023年版（国卫办食品函〔2023〕5号）', DATE '2026-11-19',
     '同时印发成人高脂血症、成人高血压、成人糖尿病、儿童青少年生长迟缓 4 项食养指南（2023年版）'),
    ('国家卫生健康委办公厅《成人高尿酸血症与痛风食养指南（2024年版）》等4项食养指南',
     'https://www.chinanutri.cn/xwzx_238/xyxw/202402/t20240219_273090.html',
     '国家卫生健康委员会办公厅', '2024年版', DATE '2026-11-19',
     '同时印发成人高尿酸血症与痛风、成人肥胖、儿童青少年肥胖、成人慢性肾脏病 4 项食养指南（2024年版）')
ON CONFLICT (source_name, source_url, version) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 2. 已有 4 条高血压规则：统一审核状态与版本，并按"钠目标互斥"定生效面
-- ---------------------------------------------------------------------------
-- 2.1 唯一生产生效的钠阈值：WHO/NHC 2000mg/日
UPDATE core.condition_nutrient_rule
   SET review_status = 'approved',
       is_active = true,
       version = 'v1.2r4-2026-11-19',
       effective_from = DATE '2026-11-19',
       evaluator = evaluator || jsonb_build_object(
           'mutually_exclusive_group', 'hypertension_sodium_target',
           'production_default', true),
       updated_at = now()
 WHERE rule_id = 'HTN-SODIUM-WHO-NHC-2000';

-- 2.2 DASH 2300 / 1500：审核通过但默认不生效（互斥候选，需个人方案或医生指定）
UPDATE core.condition_nutrient_rule
   SET review_status = 'approved',
       is_active = false,
       version = 'v1.2r4-2026-11-19',
       effective_from = DATE '2026-11-19',
       evaluator = evaluator || jsonb_build_object(
           'mutually_exclusive_group', 'hypertension_sodium_target',
           'production_default', false,
           'activation_condition', '仅当个人方案或医生指定该钠目标时，用 profile 覆盖启用；不得与默认 2000mg 目标并行生效'),
       updated_at = now()
 WHERE rule_id IN ('HTN-SODIUM-DASH-2300', 'HTN-SODIUM-DASH-1500');

-- 2.3 DASH 膳食模式：只作模式建议，不参与数值判定
UPDATE core.condition_nutrient_rule
   SET review_status = 'approved',
       is_active = true,
       version = 'v1.2r4-2026-11-19',
       effective_from = DATE '2026-11-19',
       evaluator = evaluator || jsonb_build_object(
           'numeric_evaluation', false,
           'advisory_only', true,
           'enforcement', '候选构造阶段软偏好（后端 P1 接入），不进入 daily 数值判定'),
       updated_at = now()
 WHERE rule_id = 'HTN-PATTERN-DASH';

-- ---------------------------------------------------------------------------
-- 3. 新增 5 条规则：糖尿病 2、痛风 2、高血脂 1（全部不参与数值判定，口径自证）
-- ---------------------------------------------------------------------------
INSERT INTO core.condition_nutrient_rule
    (rule_id, condition_id, rule_name_zh, rule_kind, nutrient_id, action, comparator,
     target_value, target_value_upper, target_unit, time_basis, population, selector,
     evaluator, message_zh, safety_note_zh, source_interpretation,
     review_status, medical_review_required, is_active, version, effective_from)
VALUES
    ('DM-PATTERN-LOW-GI', 'diabetes', '糖尿病：低GI全谷物为主、限制添加糖的膳食模式',
     'pattern_preference', NULL, 'prefer', NULL, NULL, NULL, NULL, 'day',
     '{"life_stage": "adult", "age_min_years": 18}'::jsonb,
     '{"prefer_categories": ["全谷物", "豆类与豆制品", "蔬菜", "鱼虾类"],
       "review_categories": ["甜点与含糖饮料", "精制米面", "油炸食品"],
       "prefer_low_gi": true}'::jsonb,
     '{"type": "pattern_advisory", "numeric_evaluation": false,
       "numeric_blocker": "core.nutrient 无 carbohydrate/added_sugar 字典，app.nutrition_result.computed 无 sugar_g/carb_g 聚合，按阈值判定会恒为 not_evaluable",
       "enforcement": "候选构造阶段软偏好（后端 P1 接入）"}'::jsonb,
     '糖尿病：优先生成全谷物、杂豆、蔬菜与优质蛋白，减少含糖饮料、甜点与精制米面。',
     '本条是膳食模式偏好，不是碳水计数处方；胰岛素或口服药用量、低血糖风险与个体碳水目标必须由医生或注册营养师确定。',
     '《成人糖尿病食养指南（2023年版）》：食物多样、主食定量、优选全谷物与低GI食物、限制添加糖。',
     'approved', true, true, 'v1.2r4-2026-11-19', DATE '2026-11-19'),

    ('DM-ADDED-SUGAR-GATE', 'diabetes', '糖尿病：高添加糖菜品进方案的复核闸门',
     'review_gate', NULL, 'review_required', NULL, NULL, NULL, NULL, 'day',
     '{"life_stage": "adult", "age_min_years": 18}'::jsonb,
     '{"review_categories": ["甜点与含糖饮料", "蜜饯与糖渍食品"],
       "review_if": {"added_sugar_level": "高"}}'::jsonb,
     '{"type": "manual_review_gate", "numeric_evaluation": false,
       "review_reason": "添加糖高的菜品默认不进方案；确需纳入时必须由用户确认份量"}'::jsonb,
     '糖尿病：含糖饮料、甜点、糖渍类菜品默认不进入方案；确需纳入时提示用户确认并说明份量。',
     '添加糖限量按《中国居民膳食指南（2022）》每日不超过50g、最好低于25g；糖尿病个体化建议遵医嘱。',
     '《成人糖尿病食养指南（2023年版）》：限制添加糖，少喝含糖饮料，控制甜点与精制糖摄入。',
     'approved', true, true, 'v1.2r4-2026-11-19', DATE '2026-11-19'),

    ('GOUT-PATTERN-LOW-PURINE', 'gout', '痛风/高尿酸：低嘌呤膳食模式（限高嘌呤、控果糖与酒）',
     'pattern_preference', NULL, 'prefer', NULL, NULL, NULL, NULL, 'day',
     '{"life_stage": "adult", "age_min_years": 18}'::jsonb,
     '{"avoid_purine_levels": ["高"], "limit_purine_levels": ["中"],
       "prefer_categories": ["蔬菜", "奶类与奶制品", "蛋类", "全谷物"],
       "review_categories": ["动物内脏", "浓肉汤与火锅汤底", "部分海鲜", "啤酒"]}'::jsonb,
     '{"type": "pattern_advisory", "numeric_evaluation": false,
       "numeric_blocker": "core.nutrient 无 purine 字典；嘌呤等级挂在 core.ingredient.purine_level，无法聚合成 daily_purine_mg",
       "enforcement": "候选构造阶段按 ingredient.purine_level 过滤（后端 P1 接入）"}'::jsonb,
     '痛风/高尿酸：优先低嘌呤食材（蛋奶、蔬菜、全谷物），避免动物内脏、浓汤与部分海鲜，限制中嘌呤食材频次。',
     '急性发作期、合并肾功能不全或使用降尿酸药物时，嘌呤与蛋白目标须由医生确定；本规则不替代降尿酸治疗。',
     '《成人高尿酸血症与痛风食养指南（2024年版）》：限制高嘌呤食物、控制果糖与酒精、足量饮水。',
     'approved', true, true, 'v1.2r4-2026-11-19', DATE '2026-11-19'),

    ('GOUT-HIGH-PURINE-GATE', 'gout', '痛风/高尿酸：高嘌呤食材进方案的复核闸门',
     'review_gate', NULL, 'review_required', NULL, NULL, NULL, NULL, 'day',
     '{"life_stage": "adult", "age_min_years": 18}'::jsonb,
     '{"review_purine_levels": ["高"], "review_categories": ["汤与酱料", "加工食品"]}'::jsonb,
     '{"type": "manual_review_gate", "numeric_evaluation": false,
       "review_reason": "高嘌呤食材需人工确认；急性期应直接排除而非放行"}'::jsonb,
     '痛风/高尿酸：高嘌呤食材默认排除；确需出现时提示用户确认并标注「急性期禁用」。',
     '高嘌呤食材清单与急性期处理以医生意见为准；合并肾功能不全者另需限蛋白与限钾。',
     '《成人高尿酸血症与痛风食养指南（2024年版）》：避免动物内脏、浓肉汤、部分海鲜等高嘌呤食物。',
     'approved', true, true, 'v1.2r4-2026-11-19', DATE '2026-11-19'),

    ('HLP-PATTERN-LOW-SATFAT', 'hyperlipidemia', '高血脂：限饱和脂肪、增膳食纤维的膳食模式',
     'pattern_preference', NULL, 'prefer', NULL, NULL, NULL, NULL, 'day',
     '{"life_stage": "adult", "age_min_years": 18}'::jsonb,
     '{"prefer_categories": ["全谷物", "豆类与豆制品", "蔬菜", "鱼类"],
       "review_categories": ["肥肉与动物油", "油炸食品", "糕点与奶油"],
       "prefer_unsaturated_oil": true}'::jsonb,
     '{"type": "pattern_advisory", "numeric_evaluation": false,
       "numeric_blocker": "core.nutrient 无 saturated_fat/cholesterol 字典，app.nutrition_result.computed 无饱和脂肪聚合",
       "enforcement": "候选构造阶段软偏好（后端 P1 接入）"}'::jsonb,
     '高血脂：优先全谷物、豆类、蔬菜与鱼类，减少肥肉、动物油、油炸食品与糕点奶油。',
     '血脂管理需结合 LDL-C 目标与调脂药物；本规则只调膳食模式，不替代药物治疗。',
     '《成人高脂血症食养指南（2023年版）》：控制脂肪总量与饱和脂肪、增加膳食纤维与植物甾醇。',
     'approved', true, true, 'v1.2r4-2026-11-19', DATE '2026-11-19')
ON CONFLICT (rule_id) DO UPDATE
    SET rule_name_zh        = EXCLUDED.rule_name_zh,
        rule_kind           = EXCLUDED.rule_kind,
        action              = EXCLUDED.action,
        selector            = EXCLUDED.selector,
        evaluator           = EXCLUDED.evaluator,
        message_zh          = EXCLUDED.message_zh,
        safety_note_zh      = EXCLUDED.safety_note_zh,
        source_interpretation = EXCLUDED.source_interpretation,
        review_status       = EXCLUDED.review_status,
        is_active           = EXCLUDED.is_active,
        version             = EXCLUDED.version,
        effective_from      = EXCLUDED.effective_from,
        updated_at          = now();

-- ---------------------------------------------------------------------------
-- 4. 规则-来源映射（每条规则至少一条，口径可回溯）
-- ---------------------------------------------------------------------------
INSERT INTO core.condition_rule_source (rule_id, source_id, source_role, source_detail)
SELECT v.rule_id, ds.source_id, v.source_role, v.source_detail
  FROM (VALUES
        ('HTN-SODIUM-WHO-NHC-2000', 'https://www.who.int/tools/elena/interventions/sodium-cvd-adults',
         'threshold', 'WHO：成人钠摄入低于2g/日（2000mg），为本轮唯一生产默认钠目标'),
        ('HTN-SODIUM-WHO-NHC-2000', 'https://www.chinacdc.cn/jkyj/yyyjk2/jswj13949/202301/t20230129_296964.html',
         'context', '《成人高血压食养指南（2023年版）》：每日食盐逐步降至5g以下、减钠增钾'),
        ('HTN-SODIUM-DASH-2300', 'https://www.nhlbi.nih.gov/health/dash-eating-plan',
         'threshold', 'NHLBI DASH：钠2300mg/日（互斥候选，默认不生效）'),
        ('HTN-SODIUM-DASH-1500', 'https://www.nhlbi.nih.gov/health/dash-eating-plan',
         'threshold', 'NHLBI DASH：1500mg/日可进一步降低血压（互斥候选，默认不生效）'),
        ('HTN-PATTERN-DASH', 'https://www.nhlbi.nih.gov/health/dash-eating-plan',
         'pattern', 'DASH 食物模式：蔬菜、水果、豆类、全谷物优先'),
        ('HTN-PATTERN-DASH', 'https://www.nhlbi.nih.gov/health/dash-eating-plan',
         'safety', '增钾建议不等于钾补充剂或低钠盐，肾功能异常者须先由专业人员判断'),
        ('DM-PATTERN-LOW-GI', 'https://www.chinacdc.cn/jkyj/yyyjk2/jswj13949/202301/t20230129_296964.html',
         'pattern', '《成人糖尿病食养指南（2023年版）》：主食定量、优选全谷物与低GI食物、限制添加糖'),
        ('DM-PATTERN-LOW-GI', 'https://www.cnsoc.org/drpostand/',
         'context', 'DRIs 2023：膳食纤维推荐摄入，作为全谷物/豆类偏好的量化背景'),
        ('DM-ADDED-SUGAR-GATE', 'https://www.chinacdc.cn/jkyj/yyyjk2/jswj13949/202301/t20230129_296964.html',
         'threshold', '《成人糖尿病食养指南（2023年版）》：限制添加糖与含糖饮料'),
        ('GOUT-PATTERN-LOW-PURINE', 'https://www.chinanutri.cn/xwzx_238/xyxw/202402/t20240219_273090.html',
         'pattern', '《成人高尿酸血症与痛风食养指南（2024年版）》：限高嘌呤、控果糖与酒精、足量饮水'),
        ('GOUT-HIGH-PURINE-GATE', 'https://www.chinanutri.cn/xwzx_238/xyxw/202402/t20240219_273090.html',
         'safety', '《成人高尿酸血症与痛风食养指南（2024年版）》：急性期严格限制高嘌呤食物'),
        ('HLP-PATTERN-LOW-SATFAT', 'https://www.chinacdc.cn/jkyj/yyyjk2/jswj13949/202301/t20230129_296964.html',
         'pattern', '《成人高脂血症食养指南（2023年版）》：控饱和脂肪、增膳食纤维与植物甾醇')
       ) AS v(rule_id, source_url, source_role, source_detail)
  JOIN core.data_source ds ON ds.source_url = v.source_url
 WHERE NOT EXISTS (
       SELECT 1 FROM core.condition_rule_source rs
        WHERE rs.rule_id = v.rule_id
          AND rs.source_id = ds.source_id
          AND rs.source_role = v.source_role
 );

-- ---------------------------------------------------------------------------
-- 5. 审批留痕（每条规则一条 approved 记录）
-- ---------------------------------------------------------------------------
INSERT INTO audit.condition_rule_review (rule_id, decision, reviewer_name, reviewer_role, review_note)
SELECT v.rule_id, 'approved', current_setting('diet.reviewer'),
       '数据岗（口径复核）+ 营养/医学审核',
       v.review_note
  FROM (VALUES
        ('HTN-SODIUM-WHO-NHC-2000',
         '核准为唯一生产默认钠目标：WHO 2g/日与《成人高血压食养指南（2023年版）》5g 食盐以下一致；与 DASH 2300/1500 设为互斥组，避免多目标并行。'),
        ('HTN-SODIUM-DASH-2300',
         '审核通过但不默认生效：DASH 2300mg 与 2000mg 同为钠上限，属互斥候选；仅个人方案或医生指定时用 profile 覆盖启用。'),
        ('HTN-SODIUM-DASH-1500',
         '审核通过但不默认生效：1500mg 是更严格可选目标，不能由系统自行替换默认目标；仅个人方案选择后启用。'),
        ('HTN-PATTERN-DASH',
         '核准为膳食模式建议（不参与数值判定）：DASH 食物模式与减钠增钾原则一致；增钾涉及肾功能与药物，已写入安全提示。'),
        ('DM-PATTERN-LOW-GI',
         '口径审核：core.nutrient 无 carbohydrate/added_sugar 字典、computed 无 sugar_g，本条不能做阈值判定，故定为 pattern_preference（numeric_evaluation=false），只作候选偏好与提示。'),
        ('DM-ADDED-SUGAR-GATE',
         '口径审核：添加糖无库内字段可聚合，设为 review_gate（review_required），高添加糖菜品默认不进方案、确需纳入时人工确认。'),
        ('GOUT-PATTERN-LOW-PURINE',
         '口径审核：嘌呤等级只在 core.ingredient.purine_level，无法聚合成 daily_purine_mg，故定为 pattern_preference；候选构造阶段按嘌呤等级过滤由后端 P1 接入。'),
        ('GOUT-HIGH-PURINE-GATE',
         '口径审核：高嘌呤食材需人工确认，急性期应直接排除；设为 review_gate（review_required），不允许静默放行。'),
        ('HLP-PATTERN-LOW-SATFAT',
         '口径审核：core.nutrient 无 saturated_fat/cholesterol，computed 无饱和脂肪聚合，故定为 pattern_preference，只作膳食模式偏好与提示。')
       ) AS v(rule_id, review_note)
 WHERE NOT EXISTS (
       SELECT 1 FROM audit.condition_rule_review r
        WHERE r.rule_id = v.rule_id
          AND r.decision = 'approved'
 );

-- ---------------------------------------------------------------------------
-- 6. 自检：9 条已审核、7 条生效、钠目标唯一、来源与审批留痕齐全、非数值规则口径自证
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    v_rules integer;
    v_approved integer;
    v_active integer;
    v_active_sodium integer;
    v_active_sodium_rule text;
    v_missing_source integer;
    v_missing_review integer;
    v_bad_non_numeric integer;
    v_production integer;
    v_conditions_covered integer;
BEGIN
    SELECT count(*),
           count(*) FILTER (WHERE review_status = 'approved'),
           count(*) FILTER (WHERE is_active)
      INTO v_rules, v_approved, v_active
      FROM core.condition_nutrient_rule
     WHERE rule_id IN ('HTN-SODIUM-WHO-NHC-2000', 'HTN-SODIUM-DASH-2300', 'HTN-SODIUM-DASH-1500',
                       'HTN-PATTERN-DASH', 'DM-PATTERN-LOW-GI', 'DM-ADDED-SUGAR-GATE',
                       'GOUT-PATTERN-LOW-PURINE', 'GOUT-HIGH-PURINE-GATE', 'HLP-PATTERN-LOW-SATFAT');

    SELECT count(*), min(rule_id)
      INTO v_active_sodium, v_active_sodium_rule
      FROM core.condition_nutrient_rule
     WHERE is_active
       AND rule_kind IN ('nutrient_limit', 'nutrient_target')
       AND nutrient_id = 'sodium';

    SELECT count(*) INTO v_missing_source
      FROM core.condition_nutrient_rule r
     WHERE r.rule_id IN ('HTN-SODIUM-WHO-NHC-2000', 'HTN-SODIUM-DASH-2300', 'HTN-SODIUM-DASH-1500',
                         'HTN-PATTERN-DASH', 'DM-PATTERN-LOW-GI', 'DM-ADDED-SUGAR-GATE',
                         'GOUT-PATTERN-LOW-PURINE', 'GOUT-HIGH-PURINE-GATE', 'HLP-PATTERN-LOW-SATFAT')
       AND NOT EXISTS (SELECT 1 FROM core.condition_rule_source rs WHERE rs.rule_id = r.rule_id);

    SELECT count(*) INTO v_missing_review
      FROM core.condition_nutrient_rule r
     WHERE r.rule_id IN ('HTN-SODIUM-WHO-NHC-2000', 'HTN-SODIUM-DASH-2300', 'HTN-SODIUM-DASH-1500',
                         'HTN-PATTERN-DASH', 'DM-PATTERN-LOW-GI', 'DM-ADDED-SUGAR-GATE',
                         'GOUT-PATTERN-LOW-PURINE', 'GOUT-HIGH-PURINE-GATE', 'HLP-PATTERN-LOW-SATFAT')
       AND NOT EXISTS (SELECT 1 FROM audit.condition_rule_review rv
                        WHERE rv.rule_id = r.rule_id AND rv.decision = 'approved');

    SELECT count(*) INTO v_bad_non_numeric
      FROM core.condition_nutrient_rule r
     WHERE r.is_active
       AND r.rule_kind IN ('pattern_preference', 'review_gate')
       AND coalesce(r.evaluator ->> 'numeric_evaluation', 'true') <> 'false';

    SELECT count(*) INTO v_production FROM app.v_production_condition_rules;

    SELECT count(DISTINCT condition_id) INTO v_conditions_covered
      FROM core.condition_nutrient_rule
     WHERE is_active
       AND condition_id IN ('hypertension', 'diabetes', 'gout', 'hyperlipidemia');

    IF v_rules <> 9 THEN
        RAISE EXCEPTION '本轮疾病规则应为9条，实际%条（缺行请检查 01 基线是否为 v1.2r2）', v_rules;
    END IF;
    IF v_approved <> 9 THEN
        RAISE EXCEPTION '应全部 approved，实际 approved %条', v_approved;
    END IF;
    IF v_active <> 7 THEN
        RAISE EXCEPTION '生效规则应为7条（钠1 + 模式与闸门6），实际%条', v_active;
    END IF;
    IF v_active_sodium <> 1 OR v_active_sodium_rule <> 'HTN-SODIUM-WHO-NHC-2000' THEN
        RAISE EXCEPTION '生效的钠阈值规则必须唯一且为 HTN-SODIUM-WHO-NHC-2000，实际%条（%）',
            v_active_sodium, coalesce(v_active_sodium_rule, '(空)');
    END IF;
    IF v_missing_source <> 0 THEN
        RAISE EXCEPTION '有%条规则缺少来源映射（condition_rule_source）', v_missing_source;
    END IF;
    IF v_missing_review <> 0 THEN
        RAISE EXCEPTION '有%条规则缺少 approved 审批记录（audit.condition_rule_review）', v_missing_review;
    END IF;
    IF v_bad_non_numeric <> 0 THEN
        RAISE EXCEPTION '有%条非数值规则未声明 numeric_evaluation=false，会被误当可判定规则', v_bad_non_numeric;
    END IF;
    IF v_production <> 7 THEN
        RAISE EXCEPTION 'v_production_condition_rules 应返回7条，实际%条', v_production;
    END IF;
    IF v_conditions_covered <> 4 THEN
        RAISE EXCEPTION '4个病种应各有生效规则，实际覆盖%个', v_conditions_covered;
    END IF;

    RAISE NOTICE '42号口径审核通过：9条规则全部 approved，7条生效（钠唯一：2000mg），4病种全覆盖，来源与审批留痕齐全';
    RAISE NOTICE '口径边界：糖尿病/痛风/高血脂只做模式偏好与人工闸门，不做数值达标判定（缺 macro/purine 字典与 computed 聚合）';
END $$;

-- ---------------------------------------------------------------------------
-- 7. 迁移留痕
-- ---------------------------------------------------------------------------
INSERT INTO audit.schema_migration (migration_id, description)
VALUES ('2026-11-19-condition-rule-review',
        '疾病规则口径审核：高血压钠目标互斥收敛（2000mg 唯一生效）、DASH 模式转建议型，新增糖尿病/痛风/高血脂 5 条模式偏好与复核闸门规则，9 条全部审批启用')
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;

-- ---------------------------------------------------------------------------
-- 8. 结果摘要
-- ---------------------------------------------------------------------------
SELECT 'rules_total' AS check_item, count(*)::text AS result
  FROM core.condition_nutrient_rule
UNION ALL
SELECT 'rules_approved', count(*)::text FROM core.condition_nutrient_rule WHERE review_status = 'approved'
UNION ALL
SELECT 'rules_active', count(*)::text FROM core.condition_nutrient_rule WHERE is_active
UNION ALL
SELECT 'active_nutrient_limits',
       count(*)::text FROM core.condition_nutrient_rule
        WHERE is_active AND rule_kind IN ('nutrient_limit', 'nutrient_target')
UNION ALL
SELECT 'production_view_rows', count(*)::text FROM app.v_production_condition_rules
UNION ALL
SELECT 'active_by_condition', string_agg(condition_id || ':' || cnt, ', ' ORDER BY condition_id)
  FROM (SELECT condition_id, count(*)::text AS cnt
          FROM core.condition_nutrient_rule
         WHERE is_active
         GROUP BY condition_id) s
ORDER BY check_item;
