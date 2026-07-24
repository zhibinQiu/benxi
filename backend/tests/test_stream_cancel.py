"""stream_cancel 协作取消单元测试。"""

from __future__ import annotations

import asyncio

import pytest

from app.core.stream_cancel import (
    await_unless_cancelled,
    clear_stream_cancel,
    install_stream_cancel,
    is_stream_cancelled,
    mark_stream_cancelled,
    raise_if_stream_cancelled,
)


@pytest.fixture(autouse=True)
def _clean_cancel():
    clear_stream_cancel()
    yield
    clear_stream_cancel()


def test_cancel_flag_lifecycle():
    assert not is_stream_cancelled()
    ev = install_stream_cancel()
    assert not is_stream_cancelled()
    mark_stream_cancelled()
    assert ev.is_set()
    assert is_stream_cancelled()
    with pytest.raises(asyncio.CancelledError):
        raise_if_stream_cancelled()


def test_await_unless_cancelled_stops_work():
    async def _run():
        install_stream_cancel()

        async def slow():
            await asyncio.sleep(5)
            return "done"

        task = asyncio.create_task(await_unless_cancelled(slow(), poll_sec=0.05))
        await asyncio.sleep(0.08)
        mark_stream_cancelled()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(_run())
