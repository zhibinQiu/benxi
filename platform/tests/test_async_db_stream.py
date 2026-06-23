"""async_db 流式并发槽测试。"""

from __future__ import annotations

import asyncio

import pytest

from app.core import async_db
from app.core.async_db import StreamCapacityError, stream_db_slot


def test_stream_db_slot_releases(monkeypatch):
    monkeypatch.setattr(
        "app.config.get_settings",
        lambda: type(
            "S",
            (),
            {"stream_max_concurrent_per_worker": 1, "stream_acquire_timeout": 0.2},
        )(),
    )
    async_db._stream_slot_sem = None

    async def run_case():
        async with stream_db_slot():
            with pytest.raises(StreamCapacityError):
                async with stream_db_slot():
                    pass

        async def hold():
            async with stream_db_slot():
                await asyncio.sleep(0.05)

        await asyncio.gather(hold(), hold())

    asyncio.run(run_case())
    async_db._stream_slot_sem = None
