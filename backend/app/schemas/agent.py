"""知识检索（T9/T10 / API-15/16）请求与响应模型。"""
from pydantic import BaseModel, Field


class RagQueryRequest(BaseModel):
    query: str = Field(..., description="查询语句")
    top_k: int = Field(5, ge=1, le=20, description="返回片段数，默认 5")


class RagItem(BaseModel):
    doc_id: str | None = None
    title: str
    content: str
    source: str | None = None
    source_id: str | None = None
    source_url: str | None = None
    category: str | None = None
    score: float | None = None
    kind: str = "doc"  # doc | nutrient | reference | notice（notice=该营养素库内无参考值，仅提示、不含数值）
    # B7：营养参考值召回路专用。命中营养素时把 RNI/AI（含年龄分层）结构化带回，
    # 便于 Agent 直接引用数值，不必再解析 content 文本。
    reference: dict | None = None


class RagResult(BaseModel):
    items: list[RagItem]
    # 实际走的检索路径：hybrid_rrf | rrf_text_only | no_hit | func_missing
    method: str = "no_hit"
    # 排查用：has_query_vector（是否算得出查询向量）、with_emb / total_docs（库内已灌向量数）
    diag: dict | None = None


class ReverseNutritionRequest(BaseModel):
    symptoms: str = Field(..., description="症状描述，如：口角炎、夜间视力下降")
    top_k: int = Field(5, ge=1, le=20)


class ReverseNutritionResult(BaseModel):
    items: list[RagItem]
    method: str = "keyword_fallback"
    note: str
