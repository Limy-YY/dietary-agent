"""FastAPI 应用入口。

统一响应结构、业务错误码、全局异常处理见 app.core。
路由前缀约定：/api（与《后端接口契约》§2.1 一致）。
"""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import BizCode, BizError
from app.core.response import ApiResponse
from app.routers import (
    agent,
    calc,
    chat,
    conditions,
    dishes,
    health,
    ingredients,
    mealplan,
    nutrition,
    profile,
    shopping,
    users,
)

app = FastAPI(
    title="膳食搭配智能体系统 - 后端 API",
    version="0.1.0",
    description="接口契约：膳食搭配智能体系统-后端接口契约.md",
)

app.include_router(health.router, prefix="/api")
app.include_router(ingredients.router, prefix="/api")
app.include_router(dishes.router, prefix="/api")
app.include_router(calc.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(profile.router, prefix="/api")
app.include_router(nutrition.router, prefix="/api")
app.include_router(conditions.router, prefix="/api")
app.include_router(conditions.catalog_router, prefix="/api")
app.include_router(agent.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(mealplan.router, prefix="/api")
app.include_router(shopping.router, prefix="/api")


@app.exception_handler(BizError)
async def biz_error_handler(_: Request, exc: BizError) -> JSONResponse:
    body = ApiResponse(code=int(exc.code), message=exc.message, data=None).model_dump()
    return JSONResponse(status_code=exc.http_status, content=body)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    body = ApiResponse(
        code=int(BizCode.PARAM_ERROR),
        message=f"参数校验失败: {exc.errors()[:1]}",
        data=None,
    ).model_dump()
    return JSONResponse(status_code=400, content=body)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    body = ApiResponse(
        code=int(BizCode.PARAM_ERROR) if exc.status_code == 404 else int(BizCode.UNAUTHORIZED),
        message=str(exc.detail),
        data=None,
    ).model_dump()
    return JSONResponse(status_code=exc.status_code, content=body)


@app.exception_handler(Exception)
async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    body = ApiResponse(code=500, message=f"服务器内部错误: {exc}", data=None).model_dump()
    return JSONResponse(status_code=500, content=body)
