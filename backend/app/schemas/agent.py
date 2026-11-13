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
    category: str | None = None
    score: float | None = None
    kind: str = "doc"  # doc | nutrient


class RagResult(BaseModel):
    items: list[RagItem]
    method: str = "keyword_fallback"


class ReverseNutritionRequest(BaseModel):
    symptoms: str = Field(..., description="症状描述，如：口角炎、夜间视力下降")
    top_k: int = Field(5, ge=1, le=20)


class ReverseNutritionResult(BaseModel):
    items: list[RagItem]
    method: str = "keyword_fallback"
    note: str
