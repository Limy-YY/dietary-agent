"""统一响应结构：{code, message, data}，分页包装为 PageData。"""
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int
    message: str
    data: T | None = None


class PageData(BaseModel, Generic[T]):
    total: int
    page: int
    page_size: int
    items: list[T]


def api_success(data: Any = None, message: str = "ok") -> ApiResponse[Any]:
    return ApiResponse(code=0, message=message, data=data)


def page_data(items: list[Any], total: int, page: int, page_size: int) -> PageData[Any]:
    return PageData(total=total, page=page, page_size=page_size, items=items)
