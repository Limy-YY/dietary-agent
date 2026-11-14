"""Embedding 客户端（RAG 查询向量化）。

依据 Agent 岗 2026-11-14 的 Embedding 契约定稿：模型 `bge-m3`，维度 **1024 定死**
（改维度须重建 `knowledge.knowledge_doc` 的 embedding 列与 HNSW 索引）。

服务二选一，走 OpenAI 兼容 `/embeddings` 接口：
- 方案 A（默认）云端 SiliconFlow：`EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1`
- 方案 B 本地 Ollama：`EMBEDDING_BASE_URL=http://127.0.0.1:11434`（本模块自动补 `/v1`），
  `EMBEDDING_API_KEY=ollama` 占位

未配置 `EMBEDDING_API_KEY`、请求失败或维度不符时统一返回 `None`，调用方据此退化为
纯关键词 RRF（`knowledge.search_documents` 的 `p_query_embedding` 允许为 NULL）。
"""
import json
import urllib.error
import urllib.request

from app.config import get_settings


def _endpoint(base_url: str) -> str:
    """补全 OpenAI 兼容路径：SiliconFlow 的 base 已含 `/v1`，Ollama 的没有。"""
    base = base_url.rstrip("/")
    if not base.endswith("/v1"):
        base += "/v1"
    return base + "/embeddings"


def embed_text(text: str) -> list[float] | None:
    """把查询串转成 1024 维向量；不可用时返回 None（不抛异常，不阻塞检索）。"""
    if not text or not text.strip():
        return None
    settings = get_settings()
    api_key = (settings.EMBEDDING_API_KEY or "").strip()
    if not api_key:
        return None

    payload = json.dumps({"model": settings.EMBEDDING_MODEL, "input": text}).encode("utf-8")
    request = urllib.request.Request(
        _endpoint(settings.EMBEDDING_BASE_URL),
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.EMBEDDING_TIMEOUT_S) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, OSError):
        return None

    data = body.get("data") or []
    vector = data[0].get("embedding") if data else None
    if not isinstance(vector, list) or len(vector) != settings.EMBEDDING_DIM:
        return None
    return [float(x) for x in vector]


def to_pgvector_literal(vector: list[float] | None) -> str | None:
    """转 pgvector 文本字面量 `[0.1,0.2,...]`；None 直接返回 None（SQL 端即 NULL）。"""
    if vector is None:
        return None
    return "[" + ",".join(f"{x:.8f}" for x in vector) + "]"
