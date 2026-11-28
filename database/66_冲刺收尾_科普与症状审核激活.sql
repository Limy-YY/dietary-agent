-- 专业审核完成后单独执行。review_task 取 D2 或 D3，reviewer 填实际审核人。
-- D3 只给「容易疲劳 → 铁」补常见说法，沿用其已审核的参考资料。
\set ON_ERROR_STOP on
\if :{?reviewer}
\else
    \set reviewer ''
\endif
\if :{?review_task}
\else
    \set review_task ''
\endif
SELECT btrim(:'reviewer') <> '' AND :'review_task' IN ('D2', 'D3') AS valid_review,
       :'review_task' = 'D2' AS review_d2 \gset
\if :valid_review
\else
    DO $$ BEGIN RAISE EXCEPTION '请指定实际审核人 reviewer 和已审核的 review_task（D2 或 D3）'; END $$;
\endif

BEGIN;

\if :review_d2
    UPDATE knowledge.nutrient_knowledge
    SET payload = jsonb_set(payload, '{nutrition_tip}', (payload -> 'nutrition_tip') || jsonb_build_object(
            'review_status', 'approved', 'reviewer', btrim(:'reviewer'), 'reviewed_at', now()
        )),
        updated_at = now()
    WHERE nutrient_id IN ('calcium','iron','zinc','vitamin_a','vitamin_b1','vitamin_b2','vitamin_c')
      AND payload #>> '{nutrition_tip,review_status}' = 'pending';

    DO $$
    BEGIN
        IF (SELECT count(*) FROM knowledge.nutrient_knowledge
             WHERE nutrient_id IN ('calcium','iron','zinc','vitamin_a','vitamin_b1','vitamin_b2','vitamin_c')
               AND payload #>> '{nutrition_tip,review_status}' = 'approved'
               AND nullif(btrim(payload #>> '{nutrition_tip,reviewer}'), '') IS NOT NULL) <> 7 THEN
            RAISE EXCEPTION 'D2：审核前先执行 65 号脚本，确认 7 条映射齐全';
        END IF;
    END $$;
\else
    DO $$
    DECLARE
        terms CONSTANT text[] := ARRAY['精力不足', '精力不济', '精力下降', '没精神', '没有精神', '提不起劲'];
        matched integer;
    BEGIN
        PERFORM 1 FROM core.symptom_nutrient_map
         WHERE symptom = '容易疲劳' AND nutrient_id = 'iron'
           AND review_status = 'approved' AND is_active AND source_id IS NOT NULL
         FOR UPDATE;
        GET DIAGNOSTICS matched = ROW_COUNT;
        IF matched <> 1 THEN
            RAISE EXCEPTION 'D3：应恰好有 1 条已经审核激活且有来源的「容易疲劳 → 铁」记录';
        END IF;

        UPDATE core.symptom_nutrient_map m
           SET aliases = m.aliases || ARRAY(
               SELECT term FROM unnest(terms) AS a(term) WHERE NOT term = ANY(m.aliases)
           )
         WHERE m.symptom = '容易疲劳' AND m.nutrient_id = 'iron'
           AND m.review_status = 'approved' AND m.is_active
           AND NOT m.aliases @> terms;
    END $$;

    INSERT INTO audit.schema_migration (migration_id, description, applied_by)
    VALUES ('sprint-closeout-d3-fatigue-aliases', '审核激活「容易疲劳 → 铁」的 6 个别名', btrim(:'reviewer'))
    ON CONFLICT (migration_id) DO NOTHING;
\endif

COMMIT;
