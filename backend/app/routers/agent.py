"""知识检索接口（T9/T10 / API-15/16）。

API-15：优先走 `knowledge.search_documents` 的 RRF 混合检索（向量路 + 关键词路，
权重 1:1、`k=60`、`top_k=5`、每路池 20）；未配置 `EMBEDDING_API_KEY` 或函数不可用时，
自动退化为纯关键词 RRF；再不行回落进程内关键词兜底，并在 `method` 字段如实标注。
T10 反向营养：symptom_nutrient_map 表待数据岗补（D3），先走知识库关键词兜底。
"""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.response import ApiResponse, api_success
from app.db import get_db
from app.schemas.agent import RagItem, RagQueryRequest, RagResult, ReverseNutritionRequest, ReverseNutritionResult
from app.services.embedding import embed_text, to_pgvector_literal

router = APIRouter(prefix="/agent", tags=["agent"])

logger = logging.getLogger(__name__)

#: 向量路最低余弦相似度，低于此值不入融合（契约默认 0.5）
_MIN_SIMILARITY = 0.5


def _search_knowledge(query: str, top_k: int, db: Session) -> list[RagItem]:
    """关键词检索：knowledge_doc 为主，nutrient_knowledge 补充。

    多词查询按空白拆分，全部词命中才返回（AND 语义）。
    score 启发式（可复算）：doc 每个词 title 命中 0.9 / 分类命中 0.5 / 正文命中 0.7，
    取词均值；nutrient 每个词 id 命中 0.8 / 内容命中 0.6，取词均值。接入向量 RRF 后替换。
    """
    terms = [t for t in query.split() if t]
    if not terms:
        return []

    def _where(cols: list[str]) -> str:
        return " AND ".join(
            "(" + " OR ".join(f"{c} ILIKE :w{i}" for c in cols) + ")"
            for i in range(len(terms))
        )

    params = {f"w{i}": f"%{t}%" for i, t in enumerate(terms)}
    params["limit"] = top_k
    n = len(terms)

    doc_weight = " + ".join(
        f"(CASE WHEN title ILIKE :w{i} THEN 0.9 WHEN category ILIKE :w{i} THEN 0.5 ELSE 0.7 END)"
        for i in range(n)
    )
    rows = db.execute(
        text(
            f"SELECT knowledge_doc_id, title, content, category, source, source_id, "
            f"({doc_weight}) / {n}::float AS score "
            f"FROM knowledge.knowledge_doc "
            f"WHERE NOT is_deleted AND {_where(['title', 'content', 'category'])} "
            f"ORDER BY score DESC, knowledge_doc_id LIMIT :limit"
        ),
        params,
    ).mappings().all()
    items = [
        RagItem(
            doc_id=str(r["knowledge_doc_id"]),
            title=r["title"],
            content=r["content"],
            source=r["source"],
            source_id=r["source_id"],
            category=r["category"],
            score=float(r["score"]) if r["score"] is not None else None,
            kind="doc",
        )
        for r in rows
    ]

    if len(items) < top_k:
        n_weight = " + ".join(
            f"(CASE WHEN nutrient_id ILIKE :w{i} THEN 0.8 ELSE 0.6 END)"
            for i in range(n)
        )
        nrows = db.execute(
            text(
                f"SELECT nutrient_id, payload::text AS content, "
                f"({n_weight}) / {n}::float AS score "
                f"FROM knowledge.nutrient_knowledge "
                f"WHERE {_where(['payload::text', 'nutrient_id'])} "
                f"ORDER BY score DESC LIMIT :limit"
            ),
            params,
        ).mappings().all()
        items.extend(
            RagItem(
                title=f"营养素知识：{r['nutrient_id']}",
                content=r["content"],
                score=float(r["score"]) if r["score"] is not None else None,
                kind="nutrient",
            )
            for r in nrows
        )
    return items


def _search_hybrid(query: str, top_k: int, db: Session) -> tuple[list[RagItem], str]:
    """RRF 混合检索（`knowledge.search_documents`），不可用时回落关键词兜底。

    返回 `(items, method)`：`hybrid_rrf` 表示向量+关键词双路融合，
    `rrf_text_only` 表示仅有查询向量缺失时的关键词路 RRF，
    `keyword_fallback` 表示检索函数不存在（未跑 14 脚本）或查询为空。
    """
    settings = get_settings()
    embedding = embed_text(query)
    sql = text(
        "SELECT knowledge_doc_id, title, category, content, score, vector_rank, text_rank "
        "FROM knowledge.search_documents("
        "CAST(:q AS text), CAST(:emb AS vector), "
        "CAST(:limit AS integer), CAST(:min_sim AS numeric), CAST(:rrf_k AS integer))"
    )
    try:
        rows = db.execute(
            sql,
            {
                "q": query,
                "emb": to_pgvector_literal(embedding),
                "limit": top_k,
                "min_sim": _MIN_SIMILARITY,
                "rrf_k": settings.RAG_RRF_K,
            },
        ).mappings().all()
    except Exception as exc:  # noqa: BLE001 —— 退化路径不能把检索接口打挂
        # 函数未部署 / 权限不足 / 维度不符：回到进程内关键词兜底，不影响出参结构
        logger.warning("search_documents 不可用，回落关键词兜底：%s", exc)
        db.rollback()
        return _search_knowledge(query, top_k, db), "keyword_fallback"

    if not rows:
        return _search_knowledge(query, top_k, db), "keyword_fallback"

    items = [
        RagItem(
            doc_id=str(r["knowledge_doc_id"]),
            title=r["title"] or "",
            content=r["content"] or "",
            category=r["category"],
            score=float(r["score"]) if r["score"] is not None else None,
            kind="doc",
        )
        for r in rows
    ]
    return items, ("hybrid_rrf" if embedding is not None else "rrf_text_only")


@router.post("/rag-query")
def rag_query(req: RagQueryRequest, db: Session = Depends(get_db)) -> ApiResponse[RagResult]:
    """RAG 知识库检索（RRF 混合检索，兼容关键词退化；每条带 doc_id 溯源）。"""
    items, method = _search_hybrid(req.query, req.top_k, db)
    return api_success(RagResult(items=items, method=method))


@router.post("/reverse-nutrition")
def reverse_nutrition(
    req: ReverseNutritionRequest, db: Session = Depends(get_db)
) -> ApiResponse[ReverseNutritionResult]:
    """反向营养推理（症状 → 营养素）：symptom_nutrient_map 待数据岗补表，
    当前走知识库关键词兜底，结果仅作线索，不得直接作为诊断依据。"""
    items = _search_knowledge(req.symptoms, req.top_k, db)
    return api_success(
        ReverseNutritionResult(
            items=items,
            note=(
                "symptom_nutrient_map 表待数据岗补排期（D3），当前结果为知识库关键词兜底，"
                "仅作参考线索，不构成医学诊断；正式推理待补表后切换"
            ),
        )
    )
