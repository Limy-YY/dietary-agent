-- v1.2r3：反向营养映射审核修订版。
-- 本批保留 13 条映射：7 条 moderate、6 条 low；全部待审核、未启用。
BEGIN;

-- 统一 Vitamin A 来源链接的大小写。已存在旧链接时直接修正，避免产生重复来源。
UPDATE core.data_source
   SET source_url = 'https://ods.od.nih.gov/factsheets/VitaminA-HealthProfessional/'
 WHERE source_url = 'https://ods.od.nih.gov/factsheets/vitamina-HealthProfessional/'
   AND NOT EXISTS (
       SELECT 1 FROM core.data_source
        WHERE source_url = 'https://ods.od.nih.gov/factsheets/VitaminA-HealthProfessional/'
   );

INSERT INTO core.data_source (source_name, source_url, publisher, version, accessed_on, notes)
SELECT v.source_name, v.source_url, v.publisher, v.version, v.accessed_on, v.notes
  FROM (VALUES
        ('NIH ODS Iron Fact Sheet', 'https://ods.od.nih.gov/factsheets/iron-HealthProfessional/', 'National Institutes of Health, Office of Dietary Supplements', '网页现行版', DATE '2026-11-15', '铁缺乏相关表现'),
        ('NIH ODS Vitamin A Fact Sheet', 'https://ods.od.nih.gov/factsheets/VitaminA-HealthProfessional/', 'National Institutes of Health, Office of Dietary Supplements', '网页现行版', DATE '2026-11-15', '维生素A缺乏相关表现'),
        ('NIH ODS Vitamin C Fact Sheet', 'https://ods.od.nih.gov/factsheets/VitaminC-HealthProfessional/', 'National Institutes of Health, Office of Dietary Supplements', '网页现行版', DATE '2026-11-15', '维生素C缺乏相关表现'),
        ('NIH ODS Riboflavin Fact Sheet', 'https://ods.od.nih.gov/factsheets/Riboflavin-HealthProfessional/', 'National Institutes of Health, Office of Dietary Supplements', '网页现行版', DATE '2026-11-15', '维生素B2缺乏相关表现'),
        ('NIH ODS Zinc Fact Sheet', 'https://ods.od.nih.gov/factsheets/Zinc-HealthProfessional/', 'National Institutes of Health, Office of Dietary Supplements', '网页现行版', DATE '2026-11-15', '锌缺乏相关表现'),
        ('NIH ODS Calcium Fact Sheet', 'https://ods.od.nih.gov/factsheets/Calcium-HealthProfessional/', 'National Institutes of Health, Office of Dietary Supplements', '网页现行版', DATE '2026-11-15', '钙摄入不足与骨健康相关资料'),
        ('NIH ODS Thiamin Fact Sheet', 'https://ods.od.nih.gov/factsheets/Thiamin-HealthProfessional/', 'National Institutes of Health, Office of Dietary Supplements', '网页现行版', DATE '2026-11-15', '维生素B1缺乏相关表现')
       ) AS v(source_name, source_url, publisher, version, accessed_on, notes)
 WHERE NOT EXISTS (SELECT 1 FROM core.data_source ds WHERE ds.source_url = v.source_url);

-- 只清理本批旧稿中仍处于待审核、未启用状态的记录。
-- 已经通过审核或已启用的记录不在本脚本中自动覆盖。
DELETE FROM core.symptom_nutrient_map
 WHERE review_status = 'pending'
   AND NOT is_reviewed
   AND NOT is_active
   AND (symptom, nutrient_id) IN (
       VALUES
       ('容易疲劳', 'iron'), ('身体无力', 'iron'), ('注意力不集中', 'iron'),
       ('夜间视物困难', 'vitamin_a'), ('眼睛干涩', 'vitamin_a'),
       ('牙龈出血', 'vitamin_c'), ('伤口愈合慢', 'vitamin_c'), ('容易出现瘀斑', 'vitamin_c'),
       ('嘴角容易破', 'vitamin_b2'), ('嘴唇肿胀开裂', 'vitamin_b2'),
       ('舌头肿痛', 'vitamin_b6'), ('舌头肿痛', 'vitamin_b2'),
       ('味觉或嗅觉减退', 'zinc'), ('骨量偏低', 'calcium'), ('容易骨折', 'calcium'),
       ('食欲下降', 'vitamin_b1'), ('记忆力下降', 'vitamin_b1')
   );

WITH mapping_rows
     (symptom, aliases, nutrient_id, advice, evidence_level, source_url) AS (
    VALUES
    ('容易疲劳', ARRAY['乏力','身体无力','虚弱','没力气','总觉得累']::text[], 'iron',
     '持续疲劳或乏力可能与铁摄入不足或缺铁有关，但也可能由睡眠、感染、贫血等其他原因造成。可关注含铁食物和近期饮食情况；症状持续或明显时建议就医检查。',
     'low', 'https://ods.od.nih.gov/factsheets/iron-HealthProfessional/'),
    ('注意力不集中', ARRAY['难以集中注意力']::text[], 'iron',
     '缺铁时可能出现注意力下降，但这一表现的原因较多。可关注含铁食物；若持续或影响日常生活，建议就医评估。',
     'low', 'https://ods.od.nih.gov/factsheets/iron-HealthProfessional/'),
    ('夜间视物困难', ARRAY['夜盲','暗处看不清']::text[], 'vitamin_a',
     '可能与维生素A不足相关，也需要排除眼科等其他原因。不要自行大剂量补充维生素A，建议及时就医检查。',
     'moderate', 'https://ods.od.nih.gov/factsheets/VitaminA-HealthProfessional/'),
    ('眼睛干涩', ARRAY['眼干']::text[], 'vitamin_a',
     '维生素A不足可能影响眼部健康，但眼干也常见于干眼症、用眼过度、环境和药物等情况。可关注饮食，症状持续时建议眼科就诊。',
     'low', 'https://ods.od.nih.gov/factsheets/VitaminA-HealthProfessional/'),
    ('牙龈出血', ARRAY['刷牙出血']::text[], 'vitamin_c',
     '长期维生素C摄入不足可能与牙龈出血有关，但也可能是牙龈炎等口腔问题。建议关注蔬果摄入并进行口腔检查。',
     'moderate', 'https://ods.od.nih.gov/factsheets/VitaminC-HealthProfessional/'),
    ('伤口愈合慢', ARRAY['伤口不容易好']::text[], 'vitamin_c',
     '维生素C不足可能影响伤口愈合，但也需考虑感染、血糖等因素。建议关注饮食，伤口异常时及时就医。',
     'moderate', 'https://ods.od.nih.gov/factsheets/VitaminC-HealthProfessional/'),
    ('容易出现瘀斑', ARRAY['容易淤青','皮下出血点']::text[], 'vitamin_c',
     '维生素C严重不足时可能出现瘀斑或出血点，但这类表现需要排除凝血异常、药物等其他原因，建议及时就医。',
     'moderate', 'https://ods.od.nih.gov/factsheets/VitaminC-HealthProfessional/'),
    ('嘴角容易破', ARRAY['口角炎','嘴角生疮']::text[], 'vitamin_b2',
     '可能与维生素B2不足相关，也可能与其他营养或局部因素有关。可关注蛋奶、瘦肉等食物；反复出现时建议就医。',
     'moderate', 'https://ods.od.nih.gov/factsheets/Riboflavin-HealthProfessional/'),
    ('嘴唇肿胀开裂', ARRAY['嘴唇干裂','唇炎']::text[], 'vitamin_b2',
     '维生素B2不足可能出现嘴唇肿胀或开裂，但不能仅凭症状判断。反复或严重时建议就医。',
     'moderate', 'https://ods.od.nih.gov/factsheets/Riboflavin-HealthProfessional/'),
    ('舌头肿痛', ARRAY['舌炎','舌头肿']::text[], 'vitamin_b2',
     '舌头肿痛可能与维生素B2、铁、维生素B12或叶酸等多种因素有关，也可能由感染或口腔疾病引起。本条仅作营养关注提示，持续或明显时建议就医检查。',
     'low', 'https://ods.od.nih.gov/factsheets/Riboflavin-HealthProfessional/'),
    ('味觉或嗅觉减退', ARRAY['味觉下降','嗅觉下降']::text[], 'zinc',
     '锌不足可能影响味觉或嗅觉，但突然或持续减退也可能有其他原因，建议及时就医评估。',
     'moderate', 'https://ods.od.nih.gov/factsheets/Zinc-HealthProfessional/'),
    ('骨量偏低', ARRAY['骨密度偏低','骨质减少','骨质疏松']::text[], 'calcium',
     '长期钙摄入不足可能影响骨量，但骨健康也受维生素D、年龄、运动和激素等因素影响。建议结合饮食情况，并按医生建议进行骨密度及相关检查。',
     'low', 'https://ods.od.nih.gov/factsheets/Calcium-HealthProfessional/'),
    ('食欲下降', ARRAY['没有食欲','食欲不振']::text[], 'vitamin_b1',
     '维生素B1不足时可能出现食欲下降，但这一表现也可能与情绪、药物、消化系统问题等有关。可关注全谷物、豆类和瘦肉等食物；持续时建议就医评估。',
     'low', 'https://ods.od.nih.gov/factsheets/Thiamin-HealthProfessional/')
)
INSERT INTO core.symptom_nutrient_map
    (symptom, aliases, nutrient_id, advice, evidence_level, source_id,
     is_reviewed, review_status, reviewer, reviewed_at, is_active)
SELECT r.symptom, r.aliases, r.nutrient_id, r.advice, r.evidence_level,
       ds.source_id, false, 'pending', NULL, NULL, false
  FROM mapping_rows r
  JOIN core.data_source ds ON ds.source_url = r.source_url;

DO $$
DECLARE
    v_count integer;
    v_moderate integer;
    v_low integer;
    v_active integer;
    v_bad_state integer;
    v_key_nutrients integer;
BEGIN
    SELECT count(*),
           count(*) FILTER (WHERE evidence_level = 'moderate'),
           count(*) FILTER (WHERE evidence_level = 'low'),
           count(*) FILTER (WHERE is_active),
           count(*) FILTER (
               WHERE review_status <> 'pending' OR is_reviewed
                  OR reviewer IS NOT NULL OR reviewed_at IS NOT NULL
                  OR source_id IS NULL OR evidence_level NOT IN ('moderate','low')
           )
      INTO v_count, v_moderate, v_low, v_active, v_bad_state
      FROM core.symptom_nutrient_map
     WHERE (symptom, nutrient_id) IN (
         VALUES
         ('容易疲劳','iron'), ('注意力不集中','iron'),
         ('夜间视物困难','vitamin_a'), ('眼睛干涩','vitamin_a'),
         ('牙龈出血','vitamin_c'), ('伤口愈合慢','vitamin_c'), ('容易出现瘀斑','vitamin_c'),
         ('嘴角容易破','vitamin_b2'), ('嘴唇肿胀开裂','vitamin_b2'), ('舌头肿痛','vitamin_b2'),
         ('味觉或嗅觉减退','zinc'), ('骨量偏低','calcium'), ('食欲下降','vitamin_b1')
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
         ('味觉或嗅觉减退','zinc'), ('骨量偏低','calcium'), ('食欲下降','vitamin_b1')
       );

    IF v_count <> 13 THEN RAISE EXCEPTION '本批反向营养映射应为13条，实际%条', v_count; END IF;
    IF v_moderate <> 7 OR v_low <> 6 THEN
        RAISE EXCEPTION '证据分级不正确：moderate %条、low %条', v_moderate, v_low;
    END IF;
    IF v_key_nutrients <> 7 THEN RAISE EXCEPTION '7种关键微量营养素覆盖不完整，实际%种', v_key_nutrients; END IF;
    IF v_active <> 0 OR v_bad_state <> 0 THEN
        RAISE EXCEPTION '待审核状态不正确：启用%条、其他异常%条', v_active, v_bad_state;
    END IF;
    IF EXISTS (
        SELECT 1 FROM core.symptom_nutrient_map
         WHERE (symptom, nutrient_id) IN (
             VALUES ('身体无力','iron'), ('容易骨折','calcium'),
                    ('记忆力下降','vitamin_b1'), ('舌头肿痛','vitamin_b6')
         )
           AND review_status = 'pending' AND NOT is_reviewed AND NOT is_active
    ) THEN
        RAISE EXCEPTION '旧版重复或低特异性映射仍有残留';
    END IF;

    RAISE NOTICE '21号审核修订通过：13条待审核映射，moderate 7条、low 6条，7种关键微量全覆盖，启用0条';
END $$;

COMMIT;
