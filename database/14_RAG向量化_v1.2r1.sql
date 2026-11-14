--
-- 14_RAG向量化_v1.2r1.sql
-- 用途：补齐评审 P1-2 缺失的 RAG 向量化整项（pgvector 扩展 + embedding 列 + 索引 + 混合检索函数）。
-- 目标环境：pgvector/pgvector:pg18 容器，库 diet_agent_v12_check，执行账号 postgres（超级用户）。
--   容器数据卷必须挂 /var/lib/postgresql——pgvector 官方的 pg18 镜像挂在 /data 上起不来。
-- 执行前提：
--   1) 镜像自带 pgvector；若 pg_available_extensions 里查不到 vector，说明镜像不对，先换镜像（第 0 段会拦下并提示）；
--   2) 库里已有 knowledge.knowledge_doc：先还原 01 备份，再跑 12_数据库整改_v1.2_to_v1.2r1.sql；
--   3) 建议在 03 之后执行：diet_app 需要 SELECT knowledge 的权限，否则它调 search_documents 会报 permission denied；
--   4) 模型与维度已按 Agent 岗 2026-11-14 的 Embedding 契约定稿：bge-m3 / 1024 维 / cosine，定后不改；
--      档案行 knowledge.embedding_profile.default 的 decision_status 记为 aligned。
-- 维度变更方式：把本文件中所有 1024 一并改成对齐后的维度，并重建 embedding 列与索引（步骤见 16 第五节）。
-- 本脚本不写入任何向量数据；向量由 15_RAG灌库脚本.py 灌入。
--

\set ON_ERROR_STOP on
\pset pager off

-- ---------------------------------------------------------------------------
-- 0. 前置校验：镜像对不对、账号够不够、库对不对（顺序即优先级，报错都能照着做）
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    v_super boolean;
    v_available boolean;
    v_installed boolean;
    v_has_doc boolean := false;
BEGIN
    SELECT r.rolsuper INTO v_super FROM pg_roles r WHERE r.rolname = current_user;
    v_available := EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'vector');
    v_installed := EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector');

    RAISE NOTICE '目标库 %，执行用户 %（超级用户=%）',
        current_database(), current_user, coalesce(v_super, false);

    IF NOT v_available THEN
        RAISE EXCEPTION '当前实例没有 pgvector（pg_available_extensions 里查不到 vector），下一句 CREATE EXTENSION 必然失败。处理办法：把容器镜像换成 pgvector/pgvector:pg18，数据卷挂 /var/lib/postgresql（不是 /data），重启容器后重跑本脚本；自建 Linux 实例按 16 说明编译安装。';
    END IF;

    IF NOT v_installed AND NOT coalesce(v_super, false) THEN
        RAISE EXCEPTION 'pgvector 可用，但当前用户 % 不是超级用户，CREATE EXTENSION 会被拒绝。请换 postgres 执行：psql -U postgres -d % -f 本脚本',
            current_user, current_database();
    END IF;

    BEGIN
        v_has_doc := to_regclass('knowledge.knowledge_doc') IS NOT NULL;
    EXCEPTION WHEN insufficient_privilege THEN
        RAISE EXCEPTION '当前用户 % 没有 schema knowledge 的访问权限，读不到 knowledge.knowledge_doc。请换 postgres 执行本脚本',
            current_user;
    END;

    IF NOT v_has_doc THEN
        RAISE EXCEPTION '当前库 % 里没有 knowledge.knowledge_doc：先还原 01 备份、并在本库跑完 12_数据库整改_v1.2_to_v1.2r1.sql，再跑本脚本',
            current_database();
    END IF;
END
$$;

CREATE EXTENSION IF NOT EXISTS vector;

COMMENT ON EXTENSION vector IS 'pgvector：knowledge_doc.embedding 的向量类型与 HNSW 索引依赖。';

-- ---------------------------------------------------------------------------
-- 1. 向量化配置档案（把"模型/维度"从代码里搬到表里，便于对齐与审计）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS knowledge.embedding_profile (
    profile_id text PRIMARY KEY,
    model_name text NOT NULL,
    dimension integer NOT NULL,
    distance_metric text NOT NULL DEFAULT 'cosine',
    is_active boolean NOT NULL DEFAULT true,
    decision_status text NOT NULL DEFAULT 'aligned',
    note text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT embedding_profile_dimension_check CHECK (dimension = 1024),
    CONSTRAINT embedding_profile_metric_check CHECK (distance_metric IN ('cosine', 'l2', 'ip')),
    CONSTRAINT embedding_profile_status_check CHECK (decision_status IN ('pending_alignment', 'aligned', 'retired'))
);

COMMENT ON TABLE knowledge.embedding_profile IS
    '嵌入配置档案：一行一个模型/维度组合。dimension 约束与 embedding 列维度绑定，改维度需同时改脚本与重建列。';

INSERT INTO knowledge.embedding_profile (profile_id, model_name, dimension, distance_metric, decision_status, note)
VALUES ('default', 'bge-m3', 1024, 'cosine', 'aligned',
        '定稿口径：bge-m3 / 1024 维 / cosine，依据 Agent 岗 2026-11-14 的 Embedding 契约；模型与维度定后不改，改维度需重建列与索引')
ON CONFLICT (profile_id) DO NOTHING;

-- 跑过旧版 14 的库，档案行还停在 pending_alignment；这里把它收敛到 aligned，
-- 免得出现"脚本说已对齐、表里状态还说没对齐"这种自相矛盾。
UPDATE knowledge.embedding_profile
   SET decision_status = 'aligned',
       is_active = true
 WHERE profile_id = 'default'
   AND decision_status = 'pending_alignment';

-- ---------------------------------------------------------------------------
-- 2. knowledge_doc 增补向量列（评审指出 v1.2 完全没有 embedding 列）
-- ---------------------------------------------------------------------------
ALTER TABLE knowledge.knowledge_doc
    ADD COLUMN IF NOT EXISTS embedding vector(1024),
    ADD COLUMN IF NOT EXISTS embedding_model text,
    ADD COLUMN IF NOT EXISTS embedding_dim integer,
    ADD COLUMN IF NOT EXISTS embedding_hash text,
    ADD COLUMN IF NOT EXISTS embedded_at timestamp with time zone;

COMMENT ON COLUMN knowledge.knowledge_doc.embedding IS '文档级向量，维度绑定 knowledge.embedding_profile.default 的 dimension（1024）。';
COMMENT ON COLUMN knowledge.knowledge_doc.embedding_model IS '实际生成该向量的模型名；与 embedding_profile 不一致时视为待重灌。';
COMMENT ON COLUMN knowledge.knowledge_doc.embedding_hash IS '生成向量时 content 的 md5；与当前 md5(content) 不一致即触发重灌（幂等去重依据）。';
COMMENT ON COLUMN knowledge.knowledge_doc.embedding_dim IS '向量维度，必须与列维度一致，用于交叉校验。';
COMMENT ON COLUMN knowledge.knowledge_doc.embedded_at IS '最后一次灌入向量的时间。';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'knowledge.knowledge_doc'::regclass
          AND conname = 'knowledge_doc_embedding_consistency_check'
    ) THEN
        ALTER TABLE knowledge.knowledge_doc
            ADD CONSTRAINT knowledge_doc_embedding_consistency_check
            CHECK (
                (embedding IS NULL AND embedding_dim IS NULL)
                OR (embedding IS NOT NULL AND embedding_dim = 1024)
            ) NOT VALID;
    END IF;
END
$$;

-- ---------------------------------------------------------------------------
-- 3. HNSW 索引（cosine 距离；语料规模在千级以下，HNSW 足够且延迟稳定）
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS knowledge_doc_embedding_hnsw
    ON knowledge.knowledge_doc
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- ---------------------------------------------------------------------------
-- 4. 混合检索（API-15）：向量召回 + 文本召回，RRF 融合
--    说明：中文无分词扩展时，文本召回退化为"子串命中 + 出现次数"打分，不引入额外扩展依赖。
--    口径按 Agent 岗契约：top_k 默认 5、RRF k=60、两路等权 1:1、每路召回池 20（本函数取 4×top_k，top_k=5 时正好 20）。
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION knowledge.search_documents(
    p_query text,
    p_query_embedding vector DEFAULT NULL,
    p_limit integer DEFAULT 5,
    p_min_similarity numeric DEFAULT 0.5,
    p_rrf_k integer DEFAULT 60
)
RETURNS TABLE(
    knowledge_doc_id bigint,
    title text,
    category text,
    content text,
    score numeric,
    vector_rank integer,
    text_rank integer,
    vector_similarity numeric
)
LANGUAGE sql
STABLE
AS $$
WITH vector_hits AS (
    SELECT d.knowledge_doc_id,
           d.title, d.category, d.content,
           (1 - (d.embedding <=> p_query_embedding))::numeric AS similarity,
           row_number() OVER (ORDER BY d.embedding <=> p_query_embedding)::integer AS rank
    FROM knowledge.knowledge_doc d
    WHERE NOT d.is_deleted
      AND p_query_embedding IS NOT NULL
      AND d.embedding IS NOT NULL
      AND (1 - (d.embedding <=> p_query_embedding)) >= p_min_similarity
    ORDER BY d.embedding <=> p_query_embedding
    LIMIT greatest(coalesce(p_limit, 5), 1) * 4
), text_hits AS (
    SELECT d.knowledge_doc_id,
           d.title, d.category, d.content,
           0::numeric AS similarity,
           row_number() OVER (
               ORDER BY (length(d.title) - length(replace(d.title, p_query, ''))) DESC,
                        (length(d.content) - length(replace(d.content, p_query, ''))) DESC,
                        d.knowledge_doc_id
           )::integer AS rank
    FROM knowledge.knowledge_doc d
    WHERE NOT d.is_deleted
      AND nullif(btrim(p_query), '') IS NOT NULL
      AND (
          d.title ILIKE '%' || btrim(p_query) || '%'
          OR d.content ILIKE '%' || btrim(p_query) || '%'
          OR d.meta_data ->> 'keywords' ILIKE '%' || btrim(p_query) || '%'
      )
    LIMIT greatest(coalesce(p_limit, 5), 1) * 4
), fused AS (
    SELECT v.knowledge_doc_id,
           max(v.title) AS title,
           max(v.category) AS category,
           max(v.content) AS content,
           sum(1.0 / (greatest(coalesce(p_rrf_k, 60), 1) + v.rank))::numeric AS vec_score,
           min(v.rank)::integer AS v_rank,
           NULL::integer AS t_rank,
           max(v.similarity)::numeric AS sim
    FROM vector_hits v
    GROUP BY v.knowledge_doc_id
), fused_text AS (
    SELECT t.knowledge_doc_id,
           max(t.title) AS title,
           max(t.category) AS category,
           max(t.content) AS content,
           sum(1.0 / (greatest(coalesce(p_rrf_k, 60), 1) + t.rank))::numeric AS text_score,
           NULL::integer AS v_rank,
           min(t.rank)::integer AS t_rank
    FROM text_hits t
    GROUP BY t.knowledge_doc_id
), combined AS (
    SELECT COALESCE(f.knowledge_doc_id, ft.knowledge_doc_id) AS knowledge_doc_id,
           COALESCE(f.title, ft.title) AS title,
           COALESCE(f.category, ft.category) AS category,
           COALESCE(f.content, ft.content) AS content,
           COALESCE(f.vec_score, 0) + COALESCE(ft.text_score, 0) AS rrf_score,
           f.v_rank, ft.t_rank, COALESCE(f.sim, 0) AS sim
    FROM fused f
    FULL JOIN fused_text ft ON ft.knowledge_doc_id = f.knowledge_doc_id
)
SELECT c.knowledge_doc_id, c.title, c.category, c.content,
       round(c.rrf_score, 6),
       c.v_rank, c.t_rank,
       round(c.sim, 4)
FROM combined c
ORDER BY c.rrf_score DESC, c.knowledge_doc_id
LIMIT least(greatest(coalesce(p_limit, 5), 1), 50)
$$;

COMMENT ON FUNCTION knowledge.search_documents(text, vector, integer, numeric, integer) IS
    'API-15 混合检索：向量召回与文本召回分别排名后按 RRF 融合；不吃中文分词扩展，缺向量时自动退化为纯文本召回。';

-- ---------------------------------------------------------------------------
-- 5. 灌库辅助：写入单条向量（供 15 脚本调用；diet_app 账号不应拥有写 knowledge 的权限）
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION knowledge.apply_document_embedding(
    p_knowledge_doc_id bigint,
    p_embedding vector,
    p_model text,
    p_content_hash text
)
RETURNS TABLE(updated_id bigint, updated_model text, updated_dim integer)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_embedding IS NULL THEN
        RAISE EXCEPTION 'embedding 不能为空';
    END IF;
    IF vector_dims(p_embedding) <> 1024 THEN
        RAISE EXCEPTION '向量维度 % 与列维度 1024 不一致', vector_dims(p_embedding);
    END IF;

    RETURN QUERY
    UPDATE knowledge.knowledge_doc d
       SET embedding = p_embedding,
           embedding_model = p_model,
           embedding_dim = vector_dims(p_embedding),
           embedding_hash = p_content_hash,
           embedded_at = now(),
           updated_at = now()
     WHERE d.knowledge_doc_id = p_knowledge_doc_id
    RETURNING d.knowledge_doc_id, d.embedding_model, d.embedding_dim;
END
$$;

COMMENT ON FUNCTION knowledge.apply_document_embedding(bigint, vector, text, text) IS
    '单条写入向量并记录模型、维度与内容 hash；维度不匹配直接报错，避免半成品数据进库。';

-- 待灌库 / 待重灌清单（内容变了 hash 也会变）
CREATE OR REPLACE VIEW knowledge.v_embedding_backlog AS
SELECT d.knowledge_doc_id,
       d.stable_key,
       d.title,
       d.category,
       d.embedding_model,
       d.embedded_at,
       (d.embedding IS NULL) AS never_embedded,
       (d.embedding IS NOT NULL AND d.embedding_hash IS DISTINCT FROM md5(d.content)) AS content_changed,
       d.content            -- 15 灌库脚本按这一列算 md5，视图必须自己带上，别让调用方再回表
FROM knowledge.knowledge_doc d
WHERE NOT d.is_deleted
  AND (
      d.embedding IS NULL
      OR d.embedding_hash IS DISTINCT FROM md5(d.content)
  );

COMMENT ON VIEW knowledge.v_embedding_backlog IS
    '待灌库清单：从未灌过，或 content 的 md5 与 embedding_hash 不一致（内容已变更需重灌）。content 列供 15 脚本算 md5，同时给出待灌文本本身。';

-- ---------------------------------------------------------------------------
-- 6. 权限：应用侧只读检索，不授予写 knowledge
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'diet_app') THEN
        GRANT SELECT ON knowledge.v_embedding_backlog TO diet_app;
        GRANT EXECUTE ON FUNCTION knowledge.search_documents(text, vector, integer, numeric, integer) TO diet_app;
    END IF;
END
$$;

-- ---------------------------------------------------------------------------
-- 7. 自检
-- ---------------------------------------------------------------------------
SELECT 'vector_extension' AS check_item,
       (SELECT extversion FROM pg_extension WHERE extname = 'vector')::text AS result
UNION ALL
SELECT 'extension_schema',
       (SELECT n.nspname FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace WHERE e.extname = 'vector')
UNION ALL
SELECT 'embedding_column', format_type(a.atttypid, a.atttypmod)
  FROM pg_attribute a
 WHERE a.attrelid = 'knowledge.knowledge_doc'::regclass AND a.attname = 'embedding'
UNION ALL
SELECT 'hnsw_index',
       (to_regclass('knowledge.knowledge_doc_embedding_hnsw') IS NOT NULL)::text
UNION ALL
SELECT 'backlog_rows', count(*)::text FROM knowledge.v_embedding_backlog
UNION ALL
SELECT 'search_function', (to_regprocedure('knowledge.search_documents(text,vector,integer,numeric,integer)') IS NOT NULL)::text
UNION ALL
SELECT 'database_name', current_database()
ORDER BY check_item;
