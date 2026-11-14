# RAG 向量化对齐与灌库说明

对应评审意见：P1-2「pgvector 补齐 RAG 向量化整项」。v1.2 原包里 `knowledge.knowledge_doc` 的
表注释写的是"嵌入模型和向量维度确认前不创建 embedding 列"——也就是说这一整块当时是留空的。
本轮把它补成可执行的方案，交付三件套：

| 文件 | 作用 |
| --- | --- |
| `14_RAG向量化_v1.2r1.sql` | 建 vector 扩展、embedding 列、HNSW 索引、配置档案表、混合检索函数、灌库辅助函数 |
| `15_RAG灌库脚本.py` | 取待灌清单 → 分批调嵌入后端 → 校验维度 → 写回，支持 dry-run 与离线导出 |
| `16_RAG对齐与灌库说明.md` | 本文，模型/维度决策、待确认清单、灌库与验收口径 |

## 一、执行状态（先讲清楚，别被误导）

- `14` 只做了 **PG18 语法解析校验**（22 条语句、0 语法错误），**没有在实例上执行过**。
- 原因：本机是 Windows，没有可用的 pgvector 二进制；EDB 免安装包在当前网络下取不到，
  Maven Central 上的 embedded-postgres 包只含服务端三个 exe，装不出扩展。
- 所以 14 的语义正确性（HNSW 参数、RRF 融合逻辑、权限语句）需要 DBA 装好扩展后跑一遍，
  跑完把输出贴回验收记录。下面的"五分钟自检"就是为此写的。
- `15` 在临时库上验证了取数、分批、维度校验、JSONL 落盘（用本地假嵌入后端跑了 3 条文档）。
  写库路径依赖 `knowledge.apply_document_embedding()` 与 `vector` 类型，同样待扩展装好后再验。

## 二、模型与维度：为什么默认 1024，怎么切 1536

评审要求"与 Agent 岗对齐后再定稿"。对齐会开完之前，代码不能空等，所以做了一个
"默认值可跑、切换只改一处"的设计：

- 默认：**bge-m3 / 1024 维 / cosine 距离**。理由：中文语料表现稳，1024 维在千级文档规模下
  索引体积与召回延迟都有余量；cosine 对归一化与否的容错最好，后期换模型不至于推翻距离口径。
- 备选：**bge-large-zh-v1.5 / 1024**、**text-embedding-3-large / 1536（可截断到 1024）**、
  **Qwen3-Embedding / 1024**。
- 维度写在两处，改的时候一起改：
  1. `14_RAG向量化_v1.2r1.sql` 里所有 `1024`（`vector(1024)` 列定义、`embedding_profile.dimension` 的
     CHECK、`apply_document_embedding` 里的维度守卫）；
  2. 环境变量 `EMBEDDING_DIM`。两者不一致时 `15` 会直接拒绝执行，不会写进半成品数据。
- 模型名与维度另有落表记录：`knowledge.embedding_profile`，一行一个组合，
  `decision_status` 从 `pending_alignment` 改成 `aligned` 就是"这个决定已经开过会了"的凭据。

## 三、待与 Agent 岗（林郑嘉）确认的清单

这四条没定，灌库就只能小批量试跑，不能全量：

| # | 问题 | 影响 | 当前默认 |
| --- | --- | --- | --- |
| 1 | 嵌入模型选哪个（bge-m3 / bge-large-zh / Qwen3-Embedding / 商用 API） | 维度、成本、离线可行性 | bge-m3 |
| 2 | 维度定 1024 还是 1536 | embedding 列与索引要重建 | 1024 |
| 3 | 文档切分粒度：整篇 `knowledge_doc.content` 一条向量，还是按段落切子块 | 若切子块，需要新增 chunk 表，本方案的列结构就不够用 | 整篇一条 |
| 4 | 召回口径：`p_min_similarity` 阈值与 top-k | 直接影响返回噪声量 | 0.5 / top-5 |

第 3 条最要紧：如果 Agent 那边打算按段落检索，`knowledge_doc` 上一条 embedding 就不合适，
需要另建 `knowledge.doc_chunk`（doc_id + chunk_no + chunk_text + embedding）。
本轮按"整篇一条向量"实现，是因为 `knowledge_doc` 现有文档都是短条目（食养指南要点、营养素说明），
整篇一条够用；这一点请在会上明确。

## 四、灌库 SOP

### 1. 装扩展（DBA，一次性）

Windows 上最省事的三种办法，按推荐顺序：

```text
A. 用官方 Docker 镜像（内部有 Docker 就用这条，最省事）
   docker run -d --name pg18-vector -e POSTGRES_PASSWORD=xxx -p 5432:5432 pgvector/pgvector:pg18
   # 镜像自带 pgvector，连上去 CREATE EXTENSION vector 即可

B. Linux 服务器上编译（生产库推荐）
   git clone --branch v0.8.0 https://github.com/pgvector/pgvector.git
   cd pgvector && make && make install   # 需要 postgresql18-server-dev

C. Windows 原生：需要 MSVC 或 MSYS2 自行编译 pgvector，官方不提供预编译包
```

装完后用这条命令确认（`14` 的第一步也是这样校验的）：

```sql
SELECT * FROM pg_available_extensions WHERE name = 'vector';
```

### 2. 建结构

```bash
psql -d diet_agent -v ON_ERROR_STOP=1 -f 14_RAG向量化_v1.2r1.sql
```

脚本末尾自带自检，正常应看到 `vector_extension / embedding_column / backlog_rows / search_function` 四行。

### 3. 先 dry-run，看清量再动手

```bash
set PGHOST=127.0.0.1
set PGPORT=5432
set PGDATABASE=diet_agent
set PGUSER=postgres
set EMBEDDING_MODE=command
set EMBEDDING_COMMAND=python C:\path\to\local_bge_m3_embed.py
python 15_RAG灌库脚本.py --dry-run
```

dry-run 只统计"待灌/待重灌多少条、预计几次调用、多少字符"，不调模型、不写库。

### 4. 小批量验证，再全量

```bash
python 15_RAG灌库脚本.py --limit 20 --batch-size 8
psql -d diet_agent -c "SELECT count(*) FROM knowledge.v_embedding_backlog"   # 应减少 20
```

确认这 20 条检索正常后再全量：

```bash
python 15_RAG灌库脚本.py --batch-size 32
```

### 5. 后端两种接法

- **api 模式**（默认）：任意 OpenAI 兼容 `/embeddings` 接口。
  `EMBEDDING_BASE_URL`、`EMBEDDING_API_KEY`、`EMBEDDING_MODEL` 三个环境变量。
  429/5xx 自动退避重试（默认 3 次）。
- **command 模式**：本地模型。命令从 stdin 读 JSONL（每行 `{"text": "..."}`），向 stdout 写
  JSONL（每行 `{"embedding": [...]}`）。这样 bge-m3 跑在本地 GPU 上也不用改脚本。

### 6. 幂等与重灌

`embedding_hash` 存的是灌库时 `content` 的 md5。`v_embedding_backlog` 的口径是：

- `never_embedded`：从没灌过；
- `content_changed`：`embedding_hash` 与当前 `md5(content)` 不一致。

所以改了文档内容，下次跑脚本会自动重灌那一条，没改的直接跳过。换模型/换维度属于"整体重灌"，
需要先清列（见下）。

## 五、改维度的完整步骤

维度不是改个常量就完事，`vector(n)` 的 n 写死在列类型里，必须重建列：

```sql
-- 1) 记下原数据，别直接丢（向量可重算，但留痕更好）
CREATE TABLE knowledge.knowledge_doc_embedding_bak AS
SELECT knowledge_doc_id, embedding, embedding_model, embedding_dim, embedding_hash, embedded_at
FROM knowledge.knowledge_doc WHERE embedding IS NOT NULL;

-- 2) 删索引、删列
DROP INDEX IF EXISTS knowledge.knowledge_doc_embedding_hnsw;
ALTER TABLE knowledge.knowledge_doc DROP COLUMN embedding;

-- 3) 改 14 里的 1024 为新维度，重跑 14（会重建列与索引）
-- 4) 全量重灌
python 15_RAG灌库脚本.py --dim <新维度> --batch-size 32

-- 5) 对比新旧召回效果后再删备份表
```

## 六、五分钟自检（扩展装好后照做）

```sql
-- ① 列与索引
SELECT format_type(a.atttypid, a.atttypmod) AS embedding_type
FROM pg_attribute a
WHERE a.attrelid = 'knowledge.knowledge_doc'::regclass AND a.attname = 'embedding';

SELECT indexname, indexdef FROM pg_indexes
WHERE schemaname = 'knowledge' AND indexname = 'knowledge_doc_embedding_hnsw';

-- ② 灌一条假向量，验证写入与维度守卫（事务内，结尾回滚）
BEGIN;
SELECT knowledge_doc_id FROM knowledge.knowledge_doc LIMIT 1 \gset
SELECT updated_id, updated_dim FROM knowledge.apply_document_embedding(
    :knowledge_doc_id,
    (SELECT ('[' || array_to_string(array_fill(0.001::float8, ARRAY[1024]), ',') || ']')::vector),
    'selftest', 'selftest'
);
ROLLBACK;

-- ③ 维度守卫是否真的会拦（期望报错，不是通过）
SELECT knowledge.apply_document_embedding(1, '[1,2,3]'::vector, 'selftest', 'x');

-- ④ 检索函数能否返回结果（没灌向量时应返回 0 行而不是报错）
SELECT count(*) FROM knowledge.search_documents('维生素', NULL, 5);
```

## 七、接口契约（给后端）

```sql
knowledge.search_documents(
    p_query           text,      -- 用户原话
    p_query_embedding vector,    -- 可为 NULL：为 NULL 时退化为纯文本召回
    p_limit           integer,   -- 默认 5，上限 50
    p_min_similarity  numeric,   -- 默认 0.5，仅作用于向量召回
    p_rrf_k           integer    -- 默认 60
) RETURNS TABLE(
    knowledge_doc_id bigint,
    title            text,
    category         text,
    content          text,
    score            numeric,    -- RRF 融合分，越大越相关
    vector_rank      integer,    -- 向量召回排名，未命中为 NULL
    text_rank        integer,    -- 文本召回排名，未命中为 NULL
    vector_similarity numeric   -- 余弦相似度，未命中为 0
)
```

三条约定：

1. **`p_query_embedding` 传 NULL 是合法调用**，走纯文本召回。这样即使扩展还没装好、
   向量还没灌完，后端也能先接上接口，不至于阻塞联调。
2. **`score` 是 RRF 分，不是相似度**，不要当阈值用；要阈值就用 `vector_similarity`。
3. **中文不分词**：文本召回用的是"子串命中 + 出现次数"，不依赖 zhparser/pg_jieba。
   好处是零扩展依赖，代价是"高血压"查不到"血压偏高"这类改写。如果要上真正的分词，
   那是另一个议题（新增扩展 + 重建索引），不在本轮范围。

## 八、遗留风险

| 风险 | 说明 | 处置 |
| --- | --- | --- |
| 14 未实测 | 无 pgvector 环境 | DBA 装扩展后按第六节自检，输出贴回 05 |
| 维度未对齐 | 等 Agent 岗开会 | 默认 1024 可先跑；改动按第五节重建 |
| 切分粒度未定 | 若改按段落切，需新增 chunk 表 | 会上确认第 3 条后，若需 chunk 表另提变更 |
| 向量质量无评测集 | 目前无法量化召回好坏 | 建议后端先把 20 条真实问句做成小评测集，再调阈值 |
