-- 为知识文档补充可核验的真实来源链接。
-- 只写入已核验的官方链接；未核实来源保持缺失，不推测。
-- 幂等：可重复执行。

\set ON_ERROR_STOP on

BEGIN;

UPDATE knowledge.knowledge_doc
SET meta_data = jsonb_set(
        COALESCE(meta_data, '{}'::jsonb),
        '{source_url}',
        to_jsonb(CASE
            WHEN source_id IN ('NHC-HTN-2023', 'NHC-DM-2023', 'NHC-HL-2023')
                THEN 'https://www.nhc.gov.cn/sps/c100088/202301/f01895a06c5349ef999f25da833c166d.shtml'
            WHEN source_id = 'DG-2022'
                THEN 'http://dg.cnsoc.org/'
        END),
        true
    ),
    updated_at = now()
WHERE source_id IN (
    'NHC-HTN-2023', 'NHC-DM-2023', 'NHC-HL-2023', 'DG-2022'
);

COMMIT;

