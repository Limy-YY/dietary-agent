-- v1.2r2：反向营养映射初稿。所有记录均为待审核、未启用。
BEGIN;

INSERT INTO core.data_source (source_name, source_url, publisher, version, accessed_on, notes)
SELECT 'NIH ODS Iron Fact Sheet', 'https://ods.od.nih.gov/factsheets/iron-HealthProfessional/', 'National Institutes of Health, Office of Dietary Supplements', '网页现行版', DATE '2026-11-15', '铁缺乏相关表现'
WHERE NOT EXISTS (SELECT 1 FROM core.data_source WHERE source_url = 'https://ods.od.nih.gov/factsheets/iron-HealthProfessional/');

INSERT INTO core.data_source (source_name, source_url, publisher, version, accessed_on, notes)
SELECT 'NIH ODS Vitamin A Fact Sheet', 'https://ods.od.nih.gov/factsheets/vitamina-HealthProfessional/', 'National Institutes of Health, Office of Dietary Supplements', '网页现行版', DATE '2026-11-15', '维生素A缺乏相关表现'
WHERE NOT EXISTS (SELECT 1 FROM core.data_source WHERE source_url = 'https://ods.od.nih.gov/factsheets/vitamina-HealthProfessional/');

INSERT INTO core.data_source (source_name, source_url, publisher, version, accessed_on, notes)
SELECT 'NIH ODS Vitamin C Fact Sheet', 'https://ods.od.nih.gov/factsheets/VitaminC-HealthProfessional/', 'National Institutes of Health, Office of Dietary Supplements', '网页现行版', DATE '2026-11-15', '维生素C缺乏相关表现'
WHERE NOT EXISTS (SELECT 1 FROM core.data_source WHERE source_url = 'https://ods.od.nih.gov/factsheets/VitaminC-HealthProfessional/');

INSERT INTO core.data_source (source_name, source_url, publisher, version, accessed_on, notes)
SELECT 'NIH ODS Riboflavin Fact Sheet', 'https://ods.od.nih.gov/factsheets/Riboflavin-HealthProfessional/', 'National Institutes of Health, Office of Dietary Supplements', '网页现行版', DATE '2026-11-15', '维生素B2缺乏相关表现'
WHERE NOT EXISTS (SELECT 1 FROM core.data_source WHERE source_url = 'https://ods.od.nih.gov/factsheets/Riboflavin-HealthProfessional/');

INSERT INTO core.data_source (source_name, source_url, publisher, version, accessed_on, notes)
SELECT 'NIH ODS Vitamin B6 Fact Sheet', 'https://ods.od.nih.gov/factsheets/VitaminB6-HealthProfessional/', 'National Institutes of Health, Office of Dietary Supplements', '网页现行版', DATE '2026-11-15', '维生素B6缺乏相关表现'
WHERE NOT EXISTS (SELECT 1 FROM core.data_source WHERE source_url = 'https://ods.od.nih.gov/factsheets/VitaminB6-HealthProfessional/');

INSERT INTO core.data_source (source_name, source_url, publisher, version, accessed_on, notes)
SELECT 'NIH ODS Zinc Fact Sheet', 'https://ods.od.nih.gov/factsheets/Zinc-HealthProfessional/', 'National Institutes of Health, Office of Dietary Supplements', '网页现行版', DATE '2026-11-15', '锌缺乏相关表现'
WHERE NOT EXISTS (SELECT 1 FROM core.data_source WHERE source_url = 'https://ods.od.nih.gov/factsheets/Zinc-HealthProfessional/');

INSERT INTO core.data_source (source_name, source_url, publisher, version, accessed_on, notes)
SELECT 'NIH ODS Calcium Fact Sheet', 'https://ods.od.nih.gov/factsheets/Calcium-HealthProfessional/', 'National Institutes of Health, Office of Dietary Supplements', '网页现行版', DATE '2026-11-15', '钙摄入不足与骨健康相关资料'
WHERE NOT EXISTS (SELECT 1 FROM core.data_source WHERE source_url = 'https://ods.od.nih.gov/factsheets/Calcium-HealthProfessional/');

INSERT INTO core.data_source (source_name, source_url, publisher, version, accessed_on, notes)
SELECT 'NIH ODS Thiamin Fact Sheet', 'https://ods.od.nih.gov/factsheets/Thiamin-HealthProfessional/', 'National Institutes of Health, Office of Dietary Supplements', '网页现行版', DATE '2026-11-15', '维生素B1缺乏相关表现'
WHERE NOT EXISTS (SELECT 1 FROM core.data_source WHERE source_url = 'https://ods.od.nih.gov/factsheets/Thiamin-HealthProfessional/');

INSERT INTO core.symptom_nutrient_map
    (symptom, aliases, nutrient_id, advice, evidence_level, source_id, is_reviewed, review_status, reviewer, reviewed_at, is_active)
SELECT '容易疲劳', ARRAY['乏力', '总觉得累']::text[], 'iron', '可能与铁摄入不足或缺铁有关，也可能有其他原因。可关注含铁食物和近期饮食情况；症状持续或明显时建议就医检查。',
       '官方资料（待专业审核）',
       (SELECT source_id FROM core.data_source WHERE source_url = 'https://ods.od.nih.gov/factsheets/iron-HealthProfessional/' ORDER BY source_id LIMIT 1),
       false, 'pending', NULL, NULL, false
WHERE NOT EXISTS (SELECT 1 FROM core.symptom_nutrient_map WHERE symptom = '容易疲劳' AND nutrient_id = 'iron');

INSERT INTO core.symptom_nutrient_map
    (symptom, aliases, nutrient_id, advice, evidence_level, source_id, is_reviewed, review_status, reviewer, reviewed_at, is_active)
SELECT '身体无力', ARRAY['虚弱', '没力气']::text[], 'iron', '可能与铁摄入不足或缺铁有关，但不能仅凭症状判断。建议结合饮食情况；持续或加重时及时就医。',
       '官方资料（待专业审核）',
       (SELECT source_id FROM core.data_source WHERE source_url = 'https://ods.od.nih.gov/factsheets/iron-HealthProfessional/' ORDER BY source_id LIMIT 1),
       false, 'pending', NULL, NULL, false
WHERE NOT EXISTS (SELECT 1 FROM core.symptom_nutrient_map WHERE symptom = '身体无力' AND nutrient_id = 'iron');

INSERT INTO core.symptom_nutrient_map
    (symptom, aliases, nutrient_id, advice, evidence_level, source_id, is_reviewed, review_status, reviewer, reviewed_at, is_active)
SELECT '注意力不集中', ARRAY['难以集中注意力']::text[], 'iron', '缺铁时可能出现注意力下降，但该表现原因较多。可关注含铁食物；若影响日常生活，建议就医评估。',
       '官方资料（待专业审核）',
       (SELECT source_id FROM core.data_source WHERE source_url = 'https://ods.od.nih.gov/factsheets/iron-HealthProfessional/' ORDER BY source_id LIMIT 1),
       false, 'pending', NULL, NULL, false
WHERE NOT EXISTS (SELECT 1 FROM core.symptom_nutrient_map WHERE symptom = '注意力不集中' AND nutrient_id = 'iron');

INSERT INTO core.symptom_nutrient_map
    (symptom, aliases, nutrient_id, advice, evidence_level, source_id, is_reviewed, review_status, reviewer, reviewed_at, is_active)
SELECT '夜间视物困难', ARRAY['夜盲', '暗处看不清']::text[], 'vitamin_a', '可能与维生素A不足相关，也需要排除眼科等其他原因。不要自行大剂量补充维生素A，建议及时就医检查。',
       '官方资料（待专业审核）',
       (SELECT source_id FROM core.data_source WHERE source_url = 'https://ods.od.nih.gov/factsheets/vitamina-HealthProfessional/' ORDER BY source_id LIMIT 1),
       false, 'pending', NULL, NULL, false
WHERE NOT EXISTS (SELECT 1 FROM core.symptom_nutrient_map WHERE symptom = '夜间视物困难' AND nutrient_id = 'vitamin_a');

INSERT INTO core.symptom_nutrient_map
    (symptom, aliases, nutrient_id, advice, evidence_level, source_id, is_reviewed, review_status, reviewer, reviewed_at, is_active)
SELECT '眼睛干涩', ARRAY['眼干']::text[], 'vitamin_a', '维生素A不足可能影响眼部健康，但眼干原因很多。可先关注饮食，症状持续时建议眼科就诊。',
       '官方资料（待专业审核）',
       (SELECT source_id FROM core.data_source WHERE source_url = 'https://ods.od.nih.gov/factsheets/vitamina-HealthProfessional/' ORDER BY source_id LIMIT 1),
       false, 'pending', NULL, NULL, false
WHERE NOT EXISTS (SELECT 1 FROM core.symptom_nutrient_map WHERE symptom = '眼睛干涩' AND nutrient_id = 'vitamin_a');

INSERT INTO core.symptom_nutrient_map
    (symptom, aliases, nutrient_id, advice, evidence_level, source_id, is_reviewed, review_status, reviewer, reviewed_at, is_active)
SELECT '牙龈出血', ARRAY['刷牙出血']::text[], 'vitamin_c', '长期维生素C摄入不足可能与牙龈出血有关，但也可能是口腔疾病等原因。建议关注蔬果摄入并进行口腔检查。',
       '官方资料（待专业审核）',
       (SELECT source_id FROM core.data_source WHERE source_url = 'https://ods.od.nih.gov/factsheets/VitaminC-HealthProfessional/' ORDER BY source_id LIMIT 1),
       false, 'pending', NULL, NULL, false
WHERE NOT EXISTS (SELECT 1 FROM core.symptom_nutrient_map WHERE symptom = '牙龈出血' AND nutrient_id = 'vitamin_c');

INSERT INTO core.symptom_nutrient_map
    (symptom, aliases, nutrient_id, advice, evidence_level, source_id, is_reviewed, review_status, reviewer, reviewed_at, is_active)
SELECT '伤口愈合慢', ARRAY['伤口不容易好']::text[], 'vitamin_c', '维生素C不足可能影响伤口愈合，但也需考虑感染、血糖等因素。建议关注饮食，伤口异常时及时就医。',
       '官方资料（待专业审核）',
       (SELECT source_id FROM core.data_source WHERE source_url = 'https://ods.od.nih.gov/factsheets/VitaminC-HealthProfessional/' ORDER BY source_id LIMIT 1),
       false, 'pending', NULL, NULL, false
WHERE NOT EXISTS (SELECT 1 FROM core.symptom_nutrient_map WHERE symptom = '伤口愈合慢' AND nutrient_id = 'vitamin_c');

INSERT INTO core.symptom_nutrient_map
    (symptom, aliases, nutrient_id, advice, evidence_level, source_id, is_reviewed, review_status, reviewer, reviewed_at, is_active)
SELECT '容易出现瘀斑', ARRAY['容易淤青', '皮下出血点']::text[], 'vitamin_c', '维生素C严重不足时可能出现瘀斑或出血点，但这类表现需要排除其他原因，建议及时就医。',
       '官方资料（待专业审核）',
       (SELECT source_id FROM core.data_source WHERE source_url = 'https://ods.od.nih.gov/factsheets/VitaminC-HealthProfessional/' ORDER BY source_id LIMIT 1),
       false, 'pending', NULL, NULL, false
WHERE NOT EXISTS (SELECT 1 FROM core.symptom_nutrient_map WHERE symptom = '容易出现瘀斑' AND nutrient_id = 'vitamin_c');

INSERT INTO core.symptom_nutrient_map
    (symptom, aliases, nutrient_id, advice, evidence_level, source_id, is_reviewed, review_status, reviewer, reviewed_at, is_active)
SELECT '嘴角容易破', ARRAY['口角炎', '嘴角生疮']::text[], 'vitamin_b2', '可能与维生素B2不足相关，也可能与其他营养或局部因素有关。可关注蛋奶、瘦肉等食物；反复出现时建议就医。',
       '官方资料（待专业审核）',
       (SELECT source_id FROM core.data_source WHERE source_url = 'https://ods.od.nih.gov/factsheets/Riboflavin-HealthProfessional/' ORDER BY source_id LIMIT 1),
       false, 'pending', NULL, NULL, false
WHERE NOT EXISTS (SELECT 1 FROM core.symptom_nutrient_map WHERE symptom = '嘴角容易破' AND nutrient_id = 'vitamin_b2');

INSERT INTO core.symptom_nutrient_map
    (symptom, aliases, nutrient_id, advice, evidence_level, source_id, is_reviewed, review_status, reviewer, reviewed_at, is_active)
SELECT '嘴唇肿胀开裂', ARRAY['嘴唇干裂', '唇炎']::text[], 'vitamin_b2', '维生素B2不足可能出现嘴唇肿胀或开裂，但不能仅凭症状判断。反复或严重时建议就医。',
       '官方资料（待专业审核）',
       (SELECT source_id FROM core.data_source WHERE source_url = 'https://ods.od.nih.gov/factsheets/Riboflavin-HealthProfessional/' ORDER BY source_id LIMIT 1),
       false, 'pending', NULL, NULL, false
WHERE NOT EXISTS (SELECT 1 FROM core.symptom_nutrient_map WHERE symptom = '嘴唇肿胀开裂' AND nutrient_id = 'vitamin_b2');

INSERT INTO core.symptom_nutrient_map
    (symptom, aliases, nutrient_id, advice, evidence_level, source_id, is_reviewed, review_status, reviewer, reviewed_at, is_active)
SELECT '舌头肿痛', ARRAY['舌炎', '舌头肿']::text[], 'vitamin_b6', '可能与维生素B6不足相关，也可能有其他原因。可关注均衡饮食；持续或伴随其他症状时建议就医。',
       '官方资料（待专业审核）',
       (SELECT source_id FROM core.data_source WHERE source_url = 'https://ods.od.nih.gov/factsheets/VitaminB6-HealthProfessional/' ORDER BY source_id LIMIT 1),
       false, 'pending', NULL, NULL, false
WHERE NOT EXISTS (SELECT 1 FROM core.symptom_nutrient_map WHERE symptom = '舌头肿痛' AND nutrient_id = 'vitamin_b6');

INSERT INTO core.symptom_nutrient_map
    (symptom, aliases, nutrient_id, advice, evidence_level, source_id, is_reviewed, review_status, reviewer, reviewed_at, is_active)
SELECT '味觉或嗅觉减退', ARRAY['味觉下降', '嗅觉下降']::text[], 'zinc', '锌不足可能影响味觉或嗅觉，但突然或持续减退也可能有其他原因，建议及时就医评估。',
       '官方资料（待专业审核）',
       (SELECT source_id FROM core.data_source WHERE source_url = 'https://ods.od.nih.gov/factsheets/Zinc-HealthProfessional/' ORDER BY source_id LIMIT 1),
       false, 'pending', NULL, NULL, false
WHERE NOT EXISTS (SELECT 1 FROM core.symptom_nutrient_map WHERE symptom = '味觉或嗅觉减退' AND nutrient_id = 'zinc');

INSERT INTO core.symptom_nutrient_map
    (symptom, aliases, nutrient_id, advice, evidence_level, source_id, is_reviewed, review_status, reviewer, reviewed_at, is_active)
SELECT '骨量偏低', ARRAY['骨密度偏低', '骨质减少']::text[], 'calcium', '长期钙摄入不足可能影响骨量，但骨量变化也受年龄、运动和激素等因素影响。建议结合饮食情况，并按医生建议进行骨健康评估。',
       'moderate',
       (SELECT source_id FROM core.data_source WHERE source_url = 'https://ods.od.nih.gov/factsheets/Calcium-HealthProfessional/' ORDER BY source_id LIMIT 1),
       false, 'pending', NULL, NULL, false
WHERE NOT EXISTS (SELECT 1 FROM core.symptom_nutrient_map WHERE symptom = '骨量偏低' AND nutrient_id = 'calcium');

INSERT INTO core.symptom_nutrient_map
    (symptom, aliases, nutrient_id, advice, evidence_level, source_id, is_reviewed, review_status, reviewer, reviewed_at, is_active)
SELECT '容易骨折', ARRAY['反复骨折', '轻微碰撞后骨折']::text[], 'calcium', '钙摄入不足可能影响骨健康，但发生骨折不能直接判断为缺钙。建议及时就医，结合骨密度和其他检查评估原因。',
       'moderate',
       (SELECT source_id FROM core.data_source WHERE source_url = 'https://ods.od.nih.gov/factsheets/Calcium-HealthProfessional/' ORDER BY source_id LIMIT 1),
       false, 'pending', NULL, NULL, false
WHERE NOT EXISTS (SELECT 1 FROM core.symptom_nutrient_map WHERE symptom = '容易骨折' AND nutrient_id = 'calcium');

INSERT INTO core.symptom_nutrient_map
    (symptom, aliases, nutrient_id, advice, evidence_level, source_id, is_reviewed, review_status, reviewer, reviewed_at, is_active)
SELECT '食欲下降', ARRAY['没有食欲', '食欲不振']::text[], 'vitamin_b1', '维生素B1不足时可能出现食欲下降，但这一表现原因很多。可关注全谷物、豆类和瘦肉等食物；持续时建议就医评估。',
       'moderate',
       (SELECT source_id FROM core.data_source WHERE source_url = 'https://ods.od.nih.gov/factsheets/Thiamin-HealthProfessional/' ORDER BY source_id LIMIT 1),
       false, 'pending', NULL, NULL, false
WHERE NOT EXISTS (SELECT 1 FROM core.symptom_nutrient_map WHERE symptom = '食欲下降' AND nutrient_id = 'vitamin_b1');

INSERT INTO core.symptom_nutrient_map
    (symptom, aliases, nutrient_id, advice, evidence_level, source_id, is_reviewed, review_status, reviewer, reviewed_at, is_active)
SELECT '记忆力下降', ARRAY['容易忘事', '短期记忆变差']::text[], 'vitamin_b1', '严重维生素B1不足可能影响认知和记忆，但记忆力下降不能直接等同于营养素缺乏。若持续或明显影响生活，建议及时就医。',
       'moderate',
       (SELECT source_id FROM core.data_source WHERE source_url = 'https://ods.od.nih.gov/factsheets/Thiamin-HealthProfessional/' ORDER BY source_id LIMIT 1),
       false, 'pending', NULL, NULL, false
WHERE NOT EXISTS (SELECT 1 FROM core.symptom_nutrient_map WHERE symptom = '记忆力下降' AND nutrient_id = 'vitamin_b1');

-- 统一为数据库约定的证据等级。待审核状态由 review_status / is_reviewed 表示，
-- 不再把“官方资料（待专业审核）”混写进 evidence_level。
UPDATE core.symptom_nutrient_map
   SET evidence_level = 'moderate'
 WHERE review_status = 'pending'
   AND evidence_level = '官方资料（待专业审核）';

DO $$
DECLARE v_count integer; v_active integer;
BEGIN
    SELECT count(*) INTO v_count FROM core.symptom_nutrient_map WHERE review_status = 'pending';
    SELECT count(*) INTO v_active FROM core.symptom_nutrient_map WHERE review_status = 'pending' AND is_active;
    IF v_active <> 0 THEN RAISE EXCEPTION '待审核反向营养映射不得启用，实际启用%条', v_active; END IF;
    RAISE NOTICE '当前待审核反向营养映射共%条，本脚本新增目标为16条，覆盖7种关键微量并保留B6补充项', v_count;
END $$;

COMMIT;
