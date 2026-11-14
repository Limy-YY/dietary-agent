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

- `14` 已在**真实 pgvector 0.8.0 实例**上执行：干净库连跑两遍，各 23 条语句、0 报错（幂等成立），
  末尾自检 7 项全部返回预期值。另外把三类前置错误各触发了一次，确认报错文案能照着改：
  没装 pgvector（提示换 `pgvector/pgvector:pg18` 镜像）、非超级用户（提示换 postgres）、
  库里没有 `knowledge_doc`（提示先还原 01 再跑 12）。
- 嵌入模型与维度已按 Agent 岗 2026-11-14 的契约书定稿（`bge-m3` / 1024 / cosine），
  `embedding_profile.decision_status` 直接落 `aligned`；跑过旧版 14 的库再跑一次会自动把
  `pending_alignment` 收敛成 `aligned`（实测：手改回 pending_alignment 跑一遍即回 aligned）。
- `15` 用本地假嵌入后端在同一个实例上跑通了**写库全链路**：3 条文档灌入 → 再跑一遍无事可做（幂等）
  → 改一条 `content` → 只重灌那 1 条，`embedding_hash` 随之更新，`v_embedding_backlog` 归零。
- 环境说明：本机（Windows）装不上 pgvector，这一轮是把 Ubuntu 云主机装的 PG14 + 编译的 pgvector 0.8.0
  当靶场跑出来的。SQL 语义与容器里的 PG18 + pgvector 0.8.x 一致，但**大版本差异仍在**：
  容器里第一次跑完请把自检输出贴回 05，作为 PG18 的正式证据。
- 跑的过程中修掉两个真问题，v1.2r1r1 之前的版本会在这两处栽：
  1. `v_embedding_backlog` 没有 `content` 列，而 15 正是从视图取 `content` 算 md5 → 一跑就报
     `column "content" does not exist`。已把 `content` 补进视图（追加在末尾，`CREATE OR REPLACE` 可就地升级）。
  2. 非超级用户先撞 schema 权限错误，看不到"该换谁跑"的提示。已把前置校验顺序改成
     镜像 → 账号 → 库，并单独兜住 `insufficient_privilege`。

## 二、模型与维度：为什么 1024，怎么切 1536

这一节原本写的是"对齐会开完之前先给默认值"，现在 Agent 岗 2026-11-14 的契约已经把模型与维度定死，
默认值就是定稿值：**bge-m3 / 1024 维 / cosine**。理由仍是那三条——中文语料稳、1024 维在千级文档
规模下索引体积与延迟都有余量、cosine 对归一化与否容错最好。

- 维度写在两处，改的时候一起改：
  1. `14_RAG向量化_v1.2r1.sql` 里所有 `1024`（`vector(1024)` 列定义、`embedding_profile.dimension` 的
     CHECK、`apply_document_embedding` 里的维度守卫）；
  2. 环境变量 `EMBEDDING_DIM`。两者不一致时 `15` 会直接拒绝执行，不会写进半成品数据。
- 契约写明"定后不改"：改维度不是改常量，要重建列与索引（第五节），还必须全量重灌。
- 模型名与维度另有落表记录：`knowledge.embedding_profile`，一行一个组合，`decision_status = aligned`
  就是"这组口径已定稿"的凭据；跑过旧版 14 的库重跑一次会自动收敛过去。

## 三、与 Agent 岗的对齐结论（2026-11-14 契约）

口径以 Agent 岗的 `embedding-contract.md` 为准。四条里定死了三条，剩一条是实现选择、需要 Agent 侧点头：

| # | 问题 | 结论 | 落在哪 |
| --- | --- | --- | --- |
| 1 | 嵌入模型 | `bge-m3`（BAAI，多语言，中文效果好） | `14` 档案表、`15` 默认值 |
| 2 | 维度 | 1024，定后不改；改维度要重建列与索引 | `14` 的 `vector(1024)`、CHECK、维度守卫 |
| 3 | 切分粒度 | 本轮按"整篇 `knowledge_doc.content` 一条向量"实现 | `14` + `15` |
| 4 | 召回口径 | top_k 5、RRF k=60、两路等权 1:1、每路召回池 20 | `14` 的 `search_documents` 默认值（池 = 4×top_k） |

第 3 条是唯一没闭环的：`knowledge_doc` 里的文档都是短条目（食养指南要点、营养素说明），整篇一条够用，
所以本轮没有建 chunk 表。如果 Agent 侧确认要按段落检索，需要另建
`knowledge.doc_chunk`（doc_id + chunk_no + chunk_text + embedding），那是结构变更，不是调参。

## 四、灌库 SOP

### 1. 装扩展（数据岗，一次性）

**容器方案（团队现在用的就是这条）**：镜像换成 `pgvector/pgvector:pg18`，镜像自带 pgvector，
`CREATE EXTENSION vector` 才执行得下去。两个坑写在前面：

- 数据卷**必须挂 `/var/lib/postgresql`**，挂 `/data` 起不来——这个镜像的 PGDATA 不在 `/data`。
- 默认的 `postgres:18` 镜像里 `pg_available_extensions` 查不到 `vector`，`14` 第一条就会抛异常，
  所以必须先换镜像，不是脚本的问题。

```bash
# 换镜像（沿用原来的卷，只改镜像与 paths）
docker stop diet-agent-pg && docker rm diet-agent-pg
docker run -d --name diet-agent-pg \
  -e POSTGRES_PASSWORD=<密码> -p 5432:5432 \
  -v <原来的数据卷>:/var/lib/postgresql \
  -v <交付包目录>:/sql \
  pgvector/pgvector:pg18
```

进去确认扩展可见（这是 `14` 第 0 段的前置条件）：

```bash
docker exec -it diet-agent-pg psql -U postgres -d diet_agent_v12_check \
  -c "SELECT name, default_version FROM pg_available_extensions WHERE name = 'vector';"
# 期望：vector | 0.8.x
```

`pgvector` 不在 `pg_available_extensions` 里时，别去改 SQL：先换镜像，换完这条能查到再往下走。

补一句：`14` 建议在 `03_应用账号与权限.sql` 跑完之后执行。`03` 里给 `diet_app` 授了
`SELECT ON ALL TABLES IN SCHEMA knowledge`，检索函数（调用者权限）读 `knowledge_doc` 靠的就是它；
顺序反了，`diet_app` 调 `search_documents` 会报 `permission denied for table knowledge_doc`。

### 2. 建结构

在容器里跑，库名认准 `diet_agent_v12_check`，账号用 `postgres`（建扩展要超级用户）：

```bash
docker exec -i diet-agent-pg psql -U postgres -d diet_agent_v12_check \
  -v ON_ERROR_STOP=1 -f /sql/14_RAG向量化_v1.2r1.sql
```

脚本幂等，跑第二遍只会看到 `already exists, skipping`。末尾自检正常应看到 **7 行**：
`backlog_rows / database_name / embedding_column / extension_schema / hnsw_index / search_function / vector_extension`，
其中 `embedding_column = vector(1024)`、`extension_schema = public`、`hnsw_index = true`。

### 3. 先 dry-run，看清量再动手

15 要写 `knowledge.knowledge_doc`（`apply_document_embedding` 是调用者权限的函数），
所以得用 `postgres` 或有 UPDATE 权限的账号跑，`diet_app` 跑不了——这是有意为之。

```bash
set PGHOST=127.0.0.1
set PGPORT=5432
set PGDATABASE=diet_agent_v12_check
set PGUSER=postgres
set EMBEDDING_MODE=command
set EMBEDDING_COMMAND=python C:\path\to\local_bge_m3_embed.py
python 15_RAG灌库脚本.py --dry-run
```

dry-run 只统计"待灌/待重灌多少条、预计几次调用、多少字符"，不调模型、不写库。
脚本在容器里跑时，`EMBEDDING_BASE_URL` 默认的 `127.0.0.1:9997` 指的是**容器自己**，
嵌入后端要填宿主机地址（`host.docker.internal:9997` 之类），否则会连不上。

### 4. 小批量验证，再全量

```bash
python 15_RAG灌库脚本.py --limit 20 --batch-size 8
docker exec -it diet-agent-pg psql -U postgres -d diet_agent_v12_check \
  -c "SELECT count(*) FROM knowledge.v_embedding_backlog"   # 应减少 20
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

### 7. 嵌入服务配置（按 Agent 岗契约，给后端）

契约给了两套，默认方案 A（云端 OpenAI 兼容，最省事）：

```env
# 方案 A（默认）：硅基流动
EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_API_KEY=<注册后领取，有免费额度>

# 方案 B（备选）：本地 Ollama
EMBEDDING_BASE_URL=http://127.0.0.1:11434
EMBEDDING_MODEL=bge-m3
EMBEDDING_API_KEY=ollama
```

这组 key 是给后端用的（初始化时灌库 + `rag-query` 查向量），跟 agent 里的 DeepSeek key 无关；
放后端 `.env`，不要提交到 git。`15` 灌库时模型名与维度要对上（默认 `bge-m3` / 1024），对不上脚本会拒跑。

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

## 六、五分钟自检（14 跑完再照做）

`14` 末尾自带 7 项结构自检（扩展版本、扩展 schema、embedding 列类型、HNSW 索引、待灌行数、
检索函数、当前库名）。这一节补的是结构之外的三件事：写入能不能落到列里、维度守卫会不会真的拦、
检索函数在没有向量时会不会报错。

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
4. **参数默认值与契约一致**：`p_limit` 默认 5、`p_rrf_k` 默认 60、两路等权 1:1，
   每路召回池 = 4 × `p_limit`（取 5 时正好 20，与契约的 `candidate_k` 对上）。调大 `p_limit` 会同比放大池子，
   超过 50 的入参会被夹到 50。

## 八、遗留风险

| 风险 | 说明 | 处置 |
| --- | --- | --- |
| 14 只在 PG14 + pgvector 0.8.0 上验过 | 容器是 PG18，大版本不同，扩展版本也可能不是 0.8.0 | 容器里首次运行后，把 7 项自检输出贴回 05 作为正式证据 |
| 切分粒度未定 | 若改按段落切，需新增 chunk 表 | 会上确认第 3 条后，若需 chunk 表另提变更 |
| 召回参数按契约写死 | 改 top_k / k / 池大小要同步改 15 与后端调用 | 契约是"定后不改"，调参走变更评审 |
| 向量质量无评测集 | 目前无法量化召回好坏 | 建议后端先把 20 条真实问句做成小评测集，再调阈值 |
