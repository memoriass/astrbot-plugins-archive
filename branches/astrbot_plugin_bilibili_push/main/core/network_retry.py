from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx

try:
    from ..utils.logger import logger
except ImportError:
    from utils.logger import logger


T = TypeVar("T")

RETRYABLE_STATUS_CODES = {408, 425, 500, 502, 503, 504}
RISK_STATUS_CODES = {403, 412}


async def retry_network_once(
    operation: Callable[[], Awaitable[T]],
    *,
    label: str,
    delay_sec: float = 0.5,
) -> T:
    try:
        return await operation()
    except Exception as exc:
        if not is_retryable_network_error(exc):
            raise
        logger.warning(f"{label} 网络异常，重试一次: {exc}")
        await asyncio.sleep(max(0.0, delay_sec))
        return await operation()


async def get_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    label: str,
    retry_statuses: set[int] | None = None,
    **kwargs,
) -> httpx.Response:
    retry_statuses = retry_statuses or RETRYABLE_STATUS_CODES
    response = await retry_network_once(
        lambda: client.get(url, **kwargs),
        label=label,
    )
    if response.status_code in RISK_STATUS_CODES:
        return response
    if response.status_code in retry_statuses:
        logger.warning(f"{label} 返回 HTTP {response.status_code}，重试一次")
        await asyncio.sleep(0.5)
        return await client.get(url, **kwargs)
    return response


def is_retryable_network_error(exc: Exception) -> bool:
    if isinstance(
        exc,
        (
            httpx.TimeoutException,
            httpx.NetworkError,
            httpx.ProtocolError,
            httpx.ProxyError,
            httpx.RemoteProtocolError,
        ),
    ):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        return status_code in RETRYABLE_STATUS_CODES
    return False
