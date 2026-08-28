"""将阻塞 IO（MySQL、pandas、pyod）移出 asyncio 事件循环。"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


async def run_blocking(fn: Callable[..., T], /, *args, **kwargs) -> T:
    return await asyncio.to_thread(fn, *args, **kwargs)
