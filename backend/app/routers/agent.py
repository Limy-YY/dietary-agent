"""知识检索接口（T9/T10 / API-15/16）。

当前实现：关键词兜底检索（knowledge_doc + nutrient_knowledge），
向量 + 关键词 RRF 混合检索待 Agent 侧 Agno Knowledge 组件接入后替换 method。
T10 反向营养：symptom_nutrient_map 表待数据岗补（D3），先走知识库关键词兜底。
"""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.response import ApiResponse, api_success
from app.db import get_db
from app.schemas.agent import RagItem, RagQueryRequest, RagResult, ReverseNutritionRequest, ReverseNutritionResult

router = APIRouter(prefix="/agent", tags=["agent"])


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


@router.post("/rag-query")
def rag_query(req: RagQueryRequest, db: Session = Depends(get_db)) -> ApiResponse[RagResult]:
    """RAG 知识库检索（关键词兜底，每条带 source 溯源）。"""
    items = _search_knowledge(req.query, req.top_k, db)
    return api_success(RagResult(items=items))


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
