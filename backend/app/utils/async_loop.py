"""Process-shared background asyncio event loop for sync callers.

graphiti-core is asyncio-only while MiroFish's Flask services are
synchronous.  This module hosts one daemon loop thread per process and
exposes a tiny synchronous bridge so services can call async libraries
without managing their own loops.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Coroutine, TypeVar

from .logger import get_logger

logger = get_logger("mirofish.async_loop")

T = TypeVar("T")

_loop: asyncio.AbstractEventLoop | None = None
_loop_lock = threading.Lock()


def get_shared_loop() -> asyncio.AbstractEventLoop:
    """Return the process-wide background event loop, starting it lazily."""

    global _loop
    if _loop is not None and not _loop.is_closed():
        return _loop

    with _loop_lock:
        if _loop is not None and not _loop.is_closed():
            return _loop

        ready = threading.Event()
        holder: dict[str, asyncio.AbstractEventLoop] = {}

        def _run() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            holder["loop"] = loop
            ready.set()
            try:
                loop.run_forever()
            finally:
                try:
                    pending = asyncio.all_tasks(loop)
                    for task in pending:
                        task.cancel()
                    loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
                    loop.run_until_complete(loop.shutdown_asyncgens())
                finally:
                    loop.close()

        thread = threading.Thread(
            target=_run,
            name="mirofish-async-loop",
            daemon=True,
        )
        thread.start()
        ready.wait(timeout=10)
        if "loop" not in holder:
            raise RuntimeError("Background asyncio loop failed to start")
        _loop = holder["loop"]
        logger.info("Background asyncio loop started")
        return _loop


def run_async(coro: Coroutine[Any, Any, T], *, timeout: float | None = None) -> T:
    """Run a coroutine on the shared loop and block until it finishes.

    Args:
        coro: The coroutine to execute.
        timeout: Optional wall-clock deadline in seconds; raises
            ``TimeoutError`` when exceeded. The coroutine is cancelled on
            timeout so background work does not accumulate.

    Returns:
        The coroutine's result.
    """

    loop = get_shared_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    try:
        return future.result(timeout=timeout)
    except (asyncio.CancelledError, TimeoutError):
        if not future.done():
            future.cancel()
        raise
    except Exception:
        if not future.done():
            future.cancel()
        raise
