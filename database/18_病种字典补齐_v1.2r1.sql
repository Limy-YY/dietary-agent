--
-- 18_病种字典补齐_v1.2r1.sql
-- 用途：core.health_condition 里只有 hypertension 一行，后端 _check_conditions 会校验 condition_id 必须在这张表里，
--       前端保存另外三种病（400「未知 condition_id」）、Agent 建档（422）都会被这一行数据卡住。本脚本补 3 行病种字典。
-- 口径：沿用 DBDD 的 4 种病，英文主键冻结为 hypertension / diabetes / hyperlipidemia / gout，改主键等于改协议，不动。
-- 前置：库里已建出 core.health_condition（01 备份恢复，或 02 结构脚本）；不需要 pgvector，任何环境可跑。
-- 执行账号：postgres，或对 core 有 INSERT/UPDATE 的账号。diet_app 没有写 core 的权限，别用它跑。
-- 幂等：ON CONFLICT 只覆盖描述性字段，不新增重复行；重复执行结果不变。
-- 边界：本脚本只补「病种字典」，不补 core.condition_nutrient_rule 的规则行——即使补齐这 3 行，
--       糖尿病/高血脂/痛风目前仍无规则可匹配，饮食约束要等规则行按审核流程启用（见 17 第五节）。
--

\set ON_ERROR_STOP on
\pset pager off

-- ---------------------------------------------------------------------------
-- 0. 前置校验：表在不在、当前账号有没有写权限，报错直接说清换谁跑
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    v_has_table boolean := false;
    v_can_write boolean;
BEGIN
    RAISE NOTICE '目标库 %，执行用户 %', current_database(), current_user;

    BEGIN
        v_has_table := to_regclass('core.health_condition') IS NOT NULL;
    EXCEPTION WHEN insufficient_privilege THEN
        RAISE EXCEPTION '当前用户 % 没有 schema core 的访问权限，读不到 core.health_condition。请换 postgres 执行本脚本',
            current_user;
    END;

    IF NOT v_has_table THEN
        RAISE EXCEPTION '当前库 % 里没有 core.health_condition：先还原 01 备份，或按 02 结构脚本建库，再跑本脚本',
            current_database();
    END IF;

    v_can_write := has_table_privilege(current_user, 'core.health_condition', 'INSERT');
    IF NOT v_can_write THEN
        RAISE EXCEPTION '当前用户 % 对 core.health_condition 没有 INSERT 权限，请换 postgres 执行：psql -U postgres -d % -f 本脚本',
            current_user, current_database();
    END IF;
END
$$;

-- ---------------------------------------------------------------------------
-- 1. 四个病种（hypertension 已存在，写成同一条语句是为了让口径统一、重复跑不新增行）
-- ---------------------------------------------------------------------------
COMMENT ON TABLE core.health_condition IS
    '病种/健康条件字典：condition_id 是英文主键，与 app.profile.conditions 的键、app.profile 校验、前端病种选项一一对应，冻结不改；一行一个病种，不含饮食规则。';

INSERT INTO core.health_condition
    (condition_id, name_zh, category, aliases, description, activation_status)
VALUES
    ('hypertension',   '高血压', '慢性疾病', ARRAY['血压升高'],
     '用于高血压相关膳食规则；只有用户 conditions.hypertension.status=confirmed 时启用。', 'confirmed'),
    ('diabetes',       '糖尿病', '慢性疾病', ARRAY['血糖升高'],
     '用于糖尿病相关膳食规则；只有用户 conditions.diabetes.status=confirmed 时启用。', 'confirmed'),
    ('hyperlipidemia', '高血脂', '慢性疾病', ARRAY['血脂升高'],
     '用于高血脂相关膳食规则；只有用户 conditions.hyperlipidemia.status=confirmed 时启用。', 'confirmed'),
    ('gout',           '痛风',   '慢性疾病', ARRAY['高尿酸', '痛风'],
     '用于痛风相关膳食规则；只有用户 conditions.gout.status=confirmed 时启用。', 'confirmed')
ON CONFLICT (condition_id) DO UPDATE
    SET name_zh           = EXCLUDED.name_zh,
        category          = EXCLUDED.category,
        aliases           = EXCLUDED.aliases,
        description       = EXCLUDED.description,
        activation_status = EXCLUDED.activation_status,
        updated_at        = now();

-- ---------------------------------------------------------------------------
-- 2. 自检：字典齐全、分类合法、都在启用状态、当前库名
-- ---------------------------------------------------------------------------
SELECT 'condition_rows' AS check_item,
       count(*)::text AS result
  FROM core.health_condition
 WHERE condition_id IN ('hypertension', 'diabetes', 'hyperlipidemia', 'gout')
UNION ALL
SELECT 'missing_condition_ids',
       coalesce(string_agg(x.id, ','), '(无)')
  FROM (VALUES ('hypertension'), ('diabetes'), ('hyperlipidemia'), ('gout')) AS x(id)
 WHERE NOT EXISTS (SELECT 1 FROM core.health_condition c WHERE c.condition_id = x.id)
UNION ALL
SELECT 'category_慢性疾病',
       count(*)::text
  FROM core.health_condition
 WHERE condition_id IN ('hypertension', 'diabetes', 'hyperlipidemia', 'gout')
   AND category = '慢性疾病'
UNION ALL
SELECT 'all_confirmed',
       count(*)::text
  FROM core.health_condition
 WHERE condition_id IN ('hypertension', 'diabetes', 'hyperlipidemia', 'gout')
   AND activation_status = 'confirmed'
UNION ALL
SELECT 'database_name', current_database()
ORDER BY check_item;
