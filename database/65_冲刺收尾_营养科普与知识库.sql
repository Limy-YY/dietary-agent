-- D2：在现有营养素映射内保存独立的待审核科普文案。
-- D4：把结构化知识的吸收、高风险人群和官方参考资料补到主检索文档。
\set ON_ERROR_STOP on
BEGIN;

WITH tips(nutrient_id, function_text, deficiency_text, foods) AS (
    VALUES
    ('calcium', '钙帮助维持骨骼和牙齿，也参与肌肉收缩。',
     '长期摄入不足会影响骨量积累，并增加骨量流失的风险。',
     ARRAY['牛奶和酸奶', '用钙盐凝固的豆腐', '连骨吃的沙丁鱼']),
    ('iron', '铁是血红蛋白的组成部分，帮助红细胞把氧送到全身。',
     '缺铁发展为缺铁性贫血时，可能出现疲劳、乏力。',
     ARRAY['瘦红肉', '贝类', '豆类']),
    ('zinc', '锌支持免疫功能，也参与伤口愈合和味觉维持。',
     '缺锌可能影响味觉和伤口愈合，儿童长期缺锌可能影响生长。',
     ARRAY['牡蛎等贝类', '牛肉', '南瓜子']),
    ('vitamin_a', '维生素A帮助眼睛适应暗处，也有助于维持正常免疫功能。',
     '缺乏时可能出现暗处视物困难，严重缺乏可损害眼睛。',
     ARRAY['鸡蛋', '胡萝卜', '红薯']),
    ('vitamin_b1', '维生素B1帮助身体利用食物中的能量，支持神经正常工作。',
     '长期缺乏可能出现肌无力或手脚麻木，严重时可引起脚气病。',
     ARRAY['瘦猪肉', '全谷物', '豆类']),
    ('vitamin_b2', '维生素B2参与能量代谢，帮助细胞正常生长和工作。',
     '缺乏时可能出现口角开裂、嘴唇干裂等表现。',
     ARRAY['牛奶和酸奶', '鸡蛋', '牛肉']),
    ('vitamin_c', '维生素C帮助合成胶原蛋白，也能促进植物性食物中铁的吸收。',
     '严重缺乏时可能出现牙龈出血、伤口愈合慢。',
     ARRAY['甜椒', '柑橘', '西兰花'])
)
UPDATE knowledge.nutrient_knowledge k
SET payload = jsonb_set(k.payload, '{nutrition_tip}', jsonb_build_object(
        'function', jsonb_build_array(t.function_text),
        'deficiency', jsonb_build_object('possible_manifestations', jsonb_build_array(t.deficiency_text)),
        'sources', to_jsonb(t.foods),
        'source', 'NIH ODS',
        'source_url', k.payload #>> '{references,0,url}',
        'review_status', 'pending'
    )),
    updated_at = now()
FROM tips t
WHERE k.nutrient_id = t.nutrient_id
  AND NOT k.payload ? 'nutrition_tip';

-- 用边界标记维护补充段，复跑可更新补充段而不会重复追加。
-- 直接沿用原资料的参考链接，纤维与钠保留各自的机构来源。
WITH supplement AS (
    SELECT d.knowledge_doc_id,
           rtrim(split_part(d.content, E'\n\n【补充资料：吸收与高风险人群】\n', 1))
           || E'\n\n【补充资料：吸收与高风险人群】\n'
           || concat_ws(E'\n',
                '促进吸收或利用：' || NULLIF(array_to_string(ARRAY(SELECT jsonb_array_elements_text(
                    k.payload #> '{absorption,enhancers}')), '；'), ''),
                '影响吸收、利用或摄入的因素：' || NULLIF(array_to_string(ARRAY(SELECT jsonb_array_elements_text(
                    k.payload #> '{absorption,inhibitors}')), '；'), ''),
                '摄入不足或缺乏风险较高的人群：' || NULLIF(array_to_string(ARRAY(SELECT jsonb_array_elements_text(
                    k.payload #> '{absorption,at_risk_groups}')), '；'), ''),
                '参考资料：' || ref.links
           ) AS content,
           ref.organization || ' · ' || d.title AS source,
           coalesce(d.meta_data, '{}'::jsonb) || jsonb_build_object(
               'source_url', ref.url,
               'original_source', coalesce(d.meta_data ->> 'original_source', d.source),
               'original_source_id', coalesce(d.meta_data ->> 'original_source_id', d.source_id)
           ) AS meta_data
      FROM knowledge.nutrient_knowledge k
      JOIN knowledge.knowledge_doc d ON d.stable_key = 'nutrient:' || k.nutrient_id || ':overview'
      CROSS JOIN LATERAL (
          SELECT (array_agg(a.ref ->> 'organization' ORDER BY a.ord))[1] AS organization,
                 (array_agg(a.ref ->> 'url' ORDER BY a.ord))[1] AS url,
                 string_agg(concat_ws(' ', a.ref ->> 'title', a.ref ->> 'url'), E'\n' ORDER BY a.ord) AS links
            FROM jsonb_array_elements(k.payload -> 'references') WITH ORDINALITY a(ref, ord)
           WHERE a.ref ->> 'url' ~ '^https://(ods\.od\.nih\.gov|www\.accessdata\.fda\.gov|medlineplus\.gov|www\.who\.int|www\.nhc\.gov\.cn)/'
      ) ref
     WHERE NOT d.is_deleted
       AND ref.url IS NOT NULL AND ref.organization IS NOT NULL
)
UPDATE knowledge.knowledge_doc d
SET content = s.content,
    source = s.source,
    source_id = NULL,
    meta_data = s.meta_data,
    embedding = CASE WHEN d.content = s.content THEN d.embedding END,
    embedding_model = CASE WHEN d.content = s.content THEN d.embedding_model END,
    embedding_dim = CASE WHEN d.content = s.content THEN d.embedding_dim END,
    embedding_hash = CASE WHEN d.content = s.content THEN d.embedding_hash END,
    embedded_at = CASE WHEN d.content = s.content THEN d.embedded_at END,
    updated_at = now()
FROM supplement s
WHERE d.knowledge_doc_id = s.knowledge_doc_id
  AND (d.content, d.source, d.source_id, d.meta_data)
      IS DISTINCT FROM (s.content, s.source, NULL::text, s.meta_data);

DO $$
BEGIN
    IF (SELECT count(*) FROM knowledge.nutrient_knowledge
         WHERE nutrient_id IN ('calcium','iron','zinc','vitamin_a','vitamin_b1','vitamin_b2','vitamin_c')
           AND coalesce(payload #>> '{nutrition_tip,source_url}', '') LIKE 'https://ods.od.nih.gov/%'
           AND payload #>> '{nutrition_tip,review_status}' IN ('pending','approved')) <> 7 THEN
        RAISE EXCEPTION 'D2：关键微量营养素科普映射未齐';
    END IF;
    IF (SELECT count(*) FROM knowledge.knowledge_doc
         WHERE stable_key LIKE 'nutrient:%:overview' AND NOT is_deleted
           AND strpos(content, '促进吸收或利用：') > 0
           AND strpos(content, '影响吸收、利用或摄入的因素：') > 0
           AND strpos(content, '摄入不足或缺乏风险较高的人群：') > 0
           AND strpos(content, '参考资料：') > 0
           AND coalesce(meta_data ->> 'source_url', '') <> '') < 26 THEN
        RAISE EXCEPTION 'D4：营养素主检索文档缺少补充内容或官方参考链接';
    END IF;
END $$;

COMMIT;
