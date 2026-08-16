"""通用工具函数:统一各服务此前各自复制的 JSON 解析与时间戳实现。

历史上 `_loads`/`_now` 在 repository、report_case、tool_queue、tool_records
中各有一份私有拷贝,且时间语义分两种(带时区 / 不带时区的 UTC)。
此处按原语义分别收编,调用方按各自原有行为选择对应函数,行为不变。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def loads_dict(value: str) -> dict[str, Any]:
    """解析 JSON 字符串为 dict,任何异常或非 dict 结果都退化为空 dict。

    面向工具队列/记录等"载荷必须是对象"的场景(原 tool_queue._loads、tool_records._loads)。
    """
    try:
        data = json.loads(value or "{}")
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def loads_or(raw: str, default: Any) -> Any:
    """解析 JSON 字符串,失败时返回调用方给定的默认值(原 repository._loads、report_case._loads)。"""
    try:
        return json.loads(raw or "")
    except Exception:
        return default


def dumps(value: Any) -> str:
    """统一 ensure_ascii=False、default=str 的 JSON 序列化(原 tool_records._json)。"""
    return json.dumps(value, ensure_ascii=False, default=str)


def now_utc() -> datetime:
    """带 UTC 时区的当前时间(原 tool_queue._now、tool_records._now)。"""
    return datetime.now(timezone.utc)


def now_utc_naive() -> datetime:
    """不带时区的 UTC 当前时间(原 repository._now、report_case._now、auth.utcnow)。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)
