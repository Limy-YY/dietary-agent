--
-- 41_反向营养映射审核激活_v1.2r4.sql
-- 用途：把 21 号写入的 13 条「审核修订后」反向营养映射正式审核激活，并补录 6 条高频症状映射，共 19 条上线。
--
-- 起点兼容（两种起点都收敛到同一结果，可重复执行）：
--   A. 已恢复 01 备份并跑过 21：库里是 13 条 pending；
--   B. 只恢复了 01 备份（未跑 21）：库里是审核前的 16 条 pending。
--   本脚本先清掉 3 类旧稿残留（身体无力/铁、容易骨折/钙、记忆力下降/B1、舌头肿痛/B6），
--   再按 37 号说明的审核文本整体重写这 19 条，因此 B 起点不会把旧稿原样激活。
--
-- 审核口径（与 37_21号反向营养映射审核修订说明.md 一致）：
--   · 容易疲劳与身体无力合并（后者进别名）；容易骨折删除（骨折是临床结局，不能直接归因缺钙）；
--     记忆力下降删除（低特异性）；舌头肿痛主映射由 B6 改为 B2（B6 非舌炎特异表现）。
--   · 证据分级：moderate = 经典缺乏表现（8 条）；low = 低特异性表现（11 条）。没有 strong：
--     症状→营养素只能作线索，不构成诊断。
--   · 新增 6 条高频症状（IMP-038）：掉发→铁、便秘→膳食纤维、失眠→镁、腿抽筋→钙、
--     口腔溃疡反复→B2、皮肤干燥→维生素A。
--
-- 执行账号：postgres，或对 core/audit 有 INSERT/UPDATE 权限的账号（diet_app 不能写 core，别用它跑）。
-- 审核人：默认写入「数据岗审核（AI 辅助复核，待责任医师签认）」，正式签认时覆盖：
--   psql -d diet_agent -v reviewer='张三（注册营养师）' -f 41_反向营养映射审核激活_v1.2r4.sql
-- 复跑：幂等。reviewed_at 保留首次审核时间，重复执行不会刷新成新时间，也不会新增重复行。
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
-- 1. 来源自足：本批 19 条映射用到的 9 个来源全部按 URL 保证存在
--    （不依赖 21 号是否跑过；21 已建的同 URL 行按唯一约束跳过，不会重复）
-- ---------------------------------------------------------------------------
-- 1.1 维生素A 链接大小写归一：已存在小写链接时直接修正，避免产生重复来源
UPDATE core.data_source
   SET source_url = 'https://ods.od.nih.gov/factsheets/VitaminA-HealthProfessional/'
 WHERE source_url = 'https://ods.od.nih.gov/factsheets/vitamina-HealthProfessional/'
   AND NOT EXISTS (
       SELECT 1 FROM core.data_source
        WHERE source_url = 'https://ods.od.nih.gov/factsheets/VitaminA-HealthProfessional/'
   );

-- 1.2 九个来源：7 条 NIH ODS + 镁 + 膳食指南
INSERT INTO core.data_source (source_name, source_url, publisher, version, accessed_on, notes)
VALUES
    ('NIH ODS Iron Fact Sheet',
     'https://ods.od.nih.gov/factsheets/iron-HealthProfessional/',
     'National Institutes of Health, Office of Dietary Supplements',
     '网页现行版', DATE '2026-11-19', '铁缺乏相关表现'),
    ('NIH ODS Vitamin A Fact Sheet',
     'https://ods.od.nih.gov/factsheets/VitaminA-HealthProfessional/',
     'National Institutes of Health, Office of Dietary Supplements',
     '网页现行版', DATE '2026-11-19', '维生素A缺乏相关表现'),
    ('NIH ODS Vitamin C Fact Sheet',
     'https://ods.od.nih.gov/factsheets/VitaminC-HealthProfessional/',
     'National Institutes of Health, Office of Dietary Supplements',
     '网页现行版', DATE '2026-11-19', '维生素C缺乏相关表现'),
    ('NIH ODS Riboflavin Fact Sheet',
     'https://ods.od.nih.gov/factsheets/Riboflavin-HealthProfessional/',
     'National Institutes of Health, Office of Dietary Supplements',
     '网页现行版', DATE '2026-11-19', '维生素B2缺乏相关表现'),
    ('NIH ODS Zinc Fact Sheet',
     'https://ods.od.nih.gov/factsheets/Zinc-HealthProfessional/',
     'National Institutes of Health, Office of Dietary Supplements',
     '网页现行版', DATE '2026-11-19', '锌缺乏相关表现'),
    ('NIH ODS Calcium Fact Sheet',
     'https://ods.od.nih.gov/factsheets/Calcium-HealthProfessional/',
     'National Institutes of Health, Office of Dietary Supplements',
     '网页现行版', DATE '2026-11-19', '钙摄入不足与骨健康相关资料'),
    ('NIH ODS Thiamin Fact Sheet',
     'https://ods.od.nih.gov/factsheets/Thiamin-HealthProfessional/',
     'National Institutes of Health, Office of Dietary Supplements',
     '网页现行版', DATE '2026-11-19', '维生素B1缺乏相关表现'),
    ('NIH ODS Magnesium Fact Sheet',
     'https://ods.od.nih.gov/factsheets/Magnesium-HealthProfessional/',
     'National Institutes of Health, Office of Dietary Supplements',
     '网页现行版', DATE '2026-11-19', '镁摄入不足与睡眠质量、肌肉痉挛相关资料'),
    ('中国营养学会《中国居民膳食指南（2022）》',
     'https://www.cnsoc.org/',
     '中国营养学会', '2022版', DATE '2026-11-19',
     '膳食纤维推荐摄入及蔬果、全谷物、豆类摄入原则（便秘相关膳食因素）')
ON CONFLICT (source_name, source_url, version) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 2. 清理 01 基线里被审核删撤的旧稿（只在仍为待审核、未启用的状态下动）
-- ---------------------------------------------------------------------------
DELETE FROM core.symptom_nutrient_map
 WHERE review_status = 'pending'
   AND NOT is_reviewed
   AND NOT is_active
   AND (symptom, nutrient_id) IN (
       VALUES
       ('身体无力', 'iron'),          -- 并入「容易疲劳」别名
       ('容易骨折', 'calcium'),       -- 骨折是临床结局，不能直接归因缺钙
       ('记忆力下降', 'vitamin_b1'),  -- 低特异性，删除
       ('舌头肿痛', 'vitamin_b6')     -- 主映射改为 B2
   );

-- ---------------------------------------------------------------------------
-- 3. 审核通过的 19 条：优先更新已有行（重写别名/说明/分级/来源并置活），缺失才插入
-- ---------------------------------------------------------------------------
WITH reviewed (symptom, aliases, nutrient_id, advice, evidence_level, source_url) AS (
    VALUES
    -- 一、21 号审核修订保留的 13 条
    ('容易疲劳',
     ARRAY['乏力','身体无力','虚弱','没力气','总觉得累']::text[], 'iron',
     '持续疲劳或乏力可能与铁摄入不足或缺铁有关，但也可能由睡眠、感染、贫血等其他原因造成。可关注含铁食物和近期饮食情况；症状持续或明显时建议就医检查。',
     'low', 'https://ods.od.nih.gov/factsheets/iron-HealthProfessional/'),
    ('注意力不集中',
     ARRAY['难以集中注意力']::text[], 'iron',
     '缺铁时可能出现注意力下降，但这一表现的原因较多。可关注含铁食物；若持续或影响日常生活，建议就医评估。',
     'low', 'https://ods.od.nih.gov/factsheets/iron-HealthProfessional/'),
    ('夜间视物困难',
     ARRAY['夜盲','暗处看不清']::text[], 'vitamin_a',
     '可能与维生素A不足相关，也需要排除眼科等其他原因。不要自行大剂量补充维生素A，建议及时就医检查。',
     'moderate', 'https://ods.od.nih.gov/factsheets/VitaminA-HealthProfessional/'),
    ('眼睛干涩',
     ARRAY['眼干']::text[], 'vitamin_a',
     '维生素A不足可能影响眼部健康，但眼干也常见于干眼症、用眼过度、环境和药物等情况。可关注饮食，症状持续时建议眼科就诊。',
     'low', 'https://ods.od.nih.gov/factsheets/VitaminA-HealthProfessional/'),
    ('牙龈出血',
     ARRAY['刷牙出血']::text[], 'vitamin_c',
     '长期维生素C摄入不足可能与牙龈出血有关，但也可能是牙龈炎等口腔问题。建议关注蔬果摄入并进行口腔检查。',
     'moderate', 'https://ods.od.nih.gov/factsheets/VitaminC-HealthProfessional/'),
    ('伤口愈合慢',
     ARRAY['伤口不容易好']::text[], 'vitamin_c',
     '维生素C不足可能影响伤口愈合，但也需考虑感染、血糖等因素。建议关注饮食，伤口异常时及时就医。',
     'moderate', 'https://ods.od.nih.gov/factsheets/VitaminC-HealthProfessional/'),
    ('容易出现瘀斑',
     ARRAY['容易淤青','皮下出血点']::text[], 'vitamin_c',
     '维生素C严重不足时可能出现瘀斑或出血点，但这类表现需要排除凝血异常、药物等其他原因，建议及时就医。',
     'moderate', 'https://ods.od.nih.gov/factsheets/VitaminC-HealthProfessional/'),
    ('嘴角容易破',
     ARRAY['口角炎','嘴角生疮']::text[], 'vitamin_b2',
     '可能与维生素B2不足相关，也可能与其他营养或局部因素有关。可关注蛋奶、瘦肉等食物；反复出现时建议就医。',
     'moderate', 'https://ods.od.nih.gov/factsheets/Riboflavin-HealthProfessional/'),
    ('嘴唇肿胀开裂',
     ARRAY['嘴唇干裂','唇炎']::text[], 'vitamin_b2',
     '维生素B2不足可能出现嘴唇肿胀或开裂，但不能仅凭症状判断。反复或严重时建议就医。',
     'moderate', 'https://ods.od.nih.gov/factsheets/Riboflavin-HealthProfessional/'),
    ('舌头肿痛',
     ARRAY['舌炎','舌头肿']::text[], 'vitamin_b2',
     '舌头肿痛可能与维生素B2、铁、维生素B12或叶酸等多种因素有关，也可能由感染或口腔疾病引起。本条仅作营养关注提示，持续或明显时建议就医检查。',
     'low', 'https://ods.od.nih.gov/factsheets/Riboflavin-HealthProfessional/'),
    ('味觉或嗅觉减退',
     ARRAY['味觉下降','嗅觉下降']::text[], 'zinc',
     '锌不足可能影响味觉或嗅觉，但突然或持续减退也可能有其他原因，建议及时就医评估。',
     'moderate', 'https://ods.od.nih.gov/factsheets/Zinc-HealthProfessional/'),
    ('骨量偏低',
     ARRAY['骨密度偏低','骨质减少','骨质疏松']::text[], 'calcium',
     '长期钙摄入不足可能影响骨量，但骨健康也受维生素D、年龄、运动和激素等因素影响。建议结合饮食情况，并按医生建议进行骨密度及相关检查。',
     'low', 'https://ods.od.nih.gov/factsheets/Calcium-HealthProfessional/'),
    ('食欲下降',
     ARRAY['没有食欲','食欲不振']::text[], 'vitamin_b1',
     '维生素B1不足时可能出现食欲下降，但这一表现也可能与情绪、药物、消化系统问题等有关。可关注全谷物、豆类和瘦肉等食物；持续时建议就医评估。',
     'low', 'https://ods.od.nih.gov/factsheets/Thiamin-HealthProfessional/'),

    -- 二、本批新增的高频症状 6 条（IMP-038）
    ('掉发',
     ARRAY['脱发','掉头发','头发掉得多','发量减少']::text[], 'iron',
     '脱发的原因很多（雄激素性脱发、休止期脱发、甲状腺问题、压力与睡眠等），缺铁只与部分脱发相关，不能仅凭掉发判断缺铁。可关注瘦肉、动物血、豆类等含铁食物与近期饮食；持续掉发、成片脱落或伴随乏力时，建议皮肤科或内科就诊，必要时查血常规与铁蛋白。',
     'low', 'https://ods.od.nih.gov/factsheets/iron-HealthProfessional/'),
    ('便秘',
     ARRAY['排便困难','大便干结','排便不畅']::text[], 'dietary_fiber',
     '膳食纤维摄入不足、饮水不足和活动量少都可能与便秘相关。可增加全谷物、杂豆、蔬菜和水果，并保证饮水；若持续不缓解、或伴随腹痛、便血、体重下降，应及时就医。',
     'moderate', 'https://www.cnsoc.org/'),
    ('失眠',
     ARRAY['睡不着','入睡困难','睡眠差','容易醒']::text[], 'magnesium',
     '镁摄入不足与睡眠质量的关联证据有限，失眠更常与压力、情绪、咖啡因、作息和疾病相关。可先规律作息、减少晚间咖啡因与屏幕时间；持续失眠建议就医，不建议自行长期服用镁补充剂。',
     'low', 'https://ods.od.nih.gov/factsheets/Magnesium-HealthProfessional/'),
    ('腿抽筋',
     ARRAY['小腿抽筋','夜里抽筋','肌肉痉挛']::text[], 'calcium',
     '夜间小腿抽筋可能与钙、镁等电解质、脱水、受凉、久站久坐或某些药物有关，老年人还需排除血管与神经因素。可关注乳制品、豆制品、深绿色蔬菜等含钙食物；频繁发作或伴水肿时建议就医。',
     'low', 'https://ods.od.nih.gov/factsheets/Calcium-HealthProfessional/'),
    ('口腔溃疡反复',
     ARRAY['口腔溃疡','口疮','嘴里起泡']::text[], 'vitamin_b2',
     '反复口腔溃疡可能与维生素B2、铁、锌、维生素B12或叶酸摄入不足有关，也常见于免疫、压力、局部创伤或口腔疾病。可关注蛋奶、瘦肉、动物肝脏与新鲜蔬果；同一处溃疡超过两周不愈，建议口腔科就诊。',
     'low', 'https://ods.od.nih.gov/factsheets/Riboflavin-HealthProfessional/'),
    ('皮肤干燥',
     ARRAY['皮肤干','皮肤粗糙','起皮']::text[], 'vitamin_a',
     '维生素A不足可能出现皮肤干燥、毛囊角化，但更常见的原因是气候干燥、过度清洁、湿疹或年龄因素。可关注动物肝脏、蛋黄、深色蔬果等；不要自行大剂量补充维生素A（有蓄积毒性），持续或伴眼干时建议就医。',
     'low', 'https://ods.od.nih.gov/factsheets/VitaminA-HealthProfessional/')
),
resolved AS (
    SELECT r.symptom, r.aliases, r.nutrient_id, r.advice, r.evidence_level, ds.source_id
      FROM reviewed r
      JOIN core.data_source ds ON ds.source_url = r.source_url
),
touched AS (
    UPDATE core.symptom_nutrient_map m
       SET aliases        = r.aliases,
           advice         = r.advice,
           evidence_level = r.evidence_level,
           source_id      = r.source_id,
           is_reviewed    = true,
           review_status  = 'approved',
           reviewer       = coalesce(m.reviewer, current_setting('diet.reviewer')),
           reviewed_at    = coalesce(m.reviewed_at, now()),
           is_active      = true
      FROM resolved r
     WHERE m.symptom = r.symptom
       AND m.nutrient_id = r.nutrient_id
    RETURNING m.symptom_nutrient_map_id
)
INSERT INTO core.symptom_nutrient_map
    (symptom, aliases, nutrient_id, advice, evidence_level, source_id,
     is_reviewed, review_status, reviewer, reviewed_at, is_active)
SELECT r.symptom, r.aliases, r.nutrient_id, r.advice, r.evidence_level, r.source_id,
       true, 'approved', current_setting('diet.reviewer'), now(), true
  FROM resolved r
 WHERE NOT EXISTS (
       SELECT 1 FROM core.symptom_nutrient_map m
        WHERE m.symptom = r.symptom
          AND m.nutrient_id = r.nutrient_id
 );

-- ---------------------------------------------------------------------------
-- 4. 自检：19 条全部已审核启用、字段齐全、分级正确、7 种关键微量全覆盖、无重复行
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    v_total integer;
    v_moderate integer;
    v_low integer;
    v_active integer;
    v_bad_state integer;
    v_pending_left integer;
    v_key_nutrients integer;
    v_dupes integer;
BEGIN
    SELECT count(*),
           count(*) FILTER (WHERE evidence_level = 'moderate'),
           count(*) FILTER (WHERE evidence_level = 'low'),
           count(*) FILTER (WHERE is_active),
           count(*) FILTER (
               WHERE review_status <> 'approved' OR NOT is_reviewed OR NOT is_active
                  OR reviewer IS NULL OR reviewed_at IS NULL OR source_id IS NULL
                  OR evidence_level NOT IN ('moderate', 'low') OR length(advice) < 20
           )
      INTO v_total, v_moderate, v_low, v_active, v_bad_state
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

    SELECT count(DISTINCT nutrient_id)
      INTO v_key_nutrients
      FROM core.symptom_nutrient_map
     WHERE nutrient_id IN ('calcium','iron','zinc','vitamin_a','vitamin_b1','vitamin_b2','vitamin_c')
       AND (symptom, nutrient_id) IN (
           VALUES
           ('容易疲劳','iron'), ('注意力不集中','iron'),
           ('夜间视物困难','vitamin_a'), ('眼睛干涩','vitamin_a'),
           ('牙龈出血','vitamin_c'), ('伤口愈合慢','vitamin_c'), ('容易出现瘀斑','vitamin_c'),
           ('嘴角容易破','vitamin_b2'), ('嘴唇肿胀开裂','vitamin_b2'), ('舌头肿痛','vitamin_b2'),
           ('味觉或嗅觉减退','zinc'), ('骨量偏低','calcium'), ('食欲下降','vitamin_b1'),
           ('掉发','iron'), ('腿抽筋','calcium'), ('口腔溃疡反复','vitamin_b2'), ('皮肤干燥','vitamin_a')
       );

    SELECT count(*) INTO v_pending_left
      FROM core.symptom_nutrient_map
     WHERE review_status = 'pending'
       AND (symptom, nutrient_id) IN (
           VALUES ('容易疲劳','iron'), ('身体无力','iron'), ('容易骨折','calcium'),
                  ('记忆力下降','vitamin_b1'), ('舌头肿痛','vitamin_b6'), ('舌头肿痛','vitamin_b2')
       );

    SELECT count(*) INTO v_dupes
      FROM (SELECT symptom, nutrient_id
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
             )
             GROUP BY symptom, nutrient_id
            HAVING count(*) > 1) d;

    IF v_total <> 19 THEN
        RAISE EXCEPTION '本批反向营养映射应为19条，实际%条', v_total;
    END IF;
    IF v_moderate <> 8 OR v_low <> 11 THEN
        RAISE EXCEPTION '证据分级不正确：moderate %条、low %条（应为 8/11）', v_moderate, v_low;
    END IF;
    IF v_active <> 19 THEN
        RAISE EXCEPTION '已启用条数不正确：应为19条，实际%条', v_active;
    END IF;
    IF v_bad_state <> 0 THEN
        RAISE EXCEPTION '有%条映射的审核字段不完整（review_status/reviewer/reviewed_at/source_id/evidence_level/advice）', v_bad_state;
    END IF;
    IF v_key_nutrients <> 7 THEN
        RAISE EXCEPTION '7种关键微量营养素覆盖不完整，实际%种', v_key_nutrients;
    END IF;
    IF v_pending_left <> 0 THEN
        RAISE EXCEPTION '本批仍残留%条待审核记录（含旧稿重复项）', v_pending_left;
    END IF;
    IF v_dupes <> 0 THEN
        RAISE EXCEPTION '症状→营养素存在%组重复映射，检索会重复召回', v_dupes;
    END IF;

    RAISE NOTICE '41号审核激活通过：19条已启用（moderate 8 / low 11），7种关键微量全覆盖，来源与审核人字段齐全，无待审核残留';
END $$;

-- ---------------------------------------------------------------------------
-- 5. 迁移与审核留痕
-- ---------------------------------------------------------------------------
INSERT INTO audit.schema_migration (migration_id, description)
VALUES ('2026-11-19-reverse-nutrition-activation',
        '反向营养映射审核激活：13条审核修订映射置 approved+is_active，新增6条高频症状映射（掉发/便秘/失眠/腿抽筋/口腔溃疡/皮肤干燥），合计19条上线')
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;

-- ---------------------------------------------------------------------------
-- 6. 结果摘要（给执行人看）
-- ---------------------------------------------------------------------------
SELECT 'symptom_map_total' AS check_item, count(*)::text AS result
  FROM core.symptom_nutrient_map
UNION ALL
SELECT 'approved', count(*)::text FROM core.symptom_nutrient_map WHERE review_status = 'approved'
UNION ALL
SELECT 'active', count(*)::text FROM core.symptom_nutrient_map WHERE is_active
UNION ALL
SELECT 'pending', count(*)::text FROM core.symptom_nutrient_map WHERE review_status = 'pending'
UNION ALL
SELECT 'moderate', count(*)::text FROM core.symptom_nutrient_map WHERE evidence_level = 'moderate'
UNION ALL
SELECT 'low', count(*)::text FROM core.symptom_nutrient_map WHERE evidence_level = 'low'
UNION ALL
SELECT 'key_nutrients',
       (SELECT count(DISTINCT nutrient_id)::text FROM core.symptom_nutrient_map
         WHERE nutrient_id IN ('calcium','iron','zinc','vitamin_a','vitamin_b1','vitamin_b2','vitamin_c'))
UNION ALL
SELECT 'reviewer', coalesce(string_agg(DISTINCT reviewer, ' / '), '(无)')
  FROM core.symptom_nutrient_map WHERE is_active
ORDER BY check_item;
