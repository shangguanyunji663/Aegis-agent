"""全局异常处理:统一 JSON 错误结构,未知异常不泄露内部细节。

分层约定:
- 路由内已知的业务错误继续显式抛 HTTPException(带准确状态码,如注册重名 409);
- 领域异常(ValueError / ToolGovernanceError)在此集中映射,路由无需逐个 try/except;
- 兜底 Exception → 500:完整堆栈写日志(带请求 ID),响应只给通用提示。
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.tools.contracts import ToolGovernanceError

logger = logging.getLogger("aegis.app.errors")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ToolGovernanceError)
    async def handle_governance(request: Request, exc: ToolGovernanceError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def handle_value_error(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": str(exc)})

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(part) for part in first.get("loc", []) if part != "body")
        detail = f"参数校验失败: {loc} {first.get('msg', 'invalid')}".strip()
        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": detail})

    @app.exception_handler(StarletteHTTPException)
    async def handle_http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=getattr(exc, "headers", None))

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        request_id = request.headers.get("X-Request-ID", "-")
        logger.exception("unhandled error on %s %s [request_id=%s]", request.method, request.url.path, request_id)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "服务器内部错误,请稍后重试"},
        )
