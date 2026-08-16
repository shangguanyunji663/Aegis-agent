"""HTTP 中间件:为每个请求/响应附加 X-Request-ID 与 X-Trace-ID 追踪头。

请求方自带同名头时沿用其值,便于网关/前端串联链路;否则生成新 ID。
"""
from __future__ import annotations

from fastapi import Request, Response

from app.core.auth import random_id


async def attach_request_context(request: Request, call_next) -> Response:
    request_id = request.headers.get("X-Request-ID") or random_id("req", 12)
    trace_id = request.headers.get("X-Trace-ID") or random_id("trace", 12)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Trace-ID"] = trace_id
    return response
