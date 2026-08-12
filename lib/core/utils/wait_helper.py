"""Polling and retry helpers for eventual consistency and transient failures.

Two distinct problems live here, and mixing them up is the usual mistake:

* **Polling** (``wait_until`` / ``wait_for_value``) — the state being checked is not
  wrong, it just hasn't arrived yet. The BE action returns before OpenSearch has
  indexed or DocumentDB has replicated, so DB/S3/OpenSearch checks poll instead of
  asserting once.
* **Retrying** (``retry`` / ``retry_on_transient_error``) — the *call itself* failed in
  a way that may not recur: a dropped connection, a 502 from a load balancer mid-deploy.

This is the only place either belongs. Per CLAUDE.md, modules must not hand-roll retry
loops, and Playwright FE steps rely on Playwright's own auto-waiting rather than these.

Every retry is logged at WARNING with the attempt number and the failure, so a run that
passed only on the third attempt is visible in the log rather than silently green.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import time
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Default retry shape, per CLAUDE.md: small fixed attempt count, exponential backoff.
DEFAULT_ATTEMPTS = 3
DEFAULT_DELAY_SECONDS = 1.0
DEFAULT_BACKOFF = 2.0

# Exception types treated as transient by default.
#
# Deliberately NOT ``(Exception,)``. Retrying everything means a deterministic
# ``AssertionError`` — a real, reproducible test failure — gets attempted three times with
# backoff, making every negative-path test slower and filling the log with WARNING
# "retrying" lines that imply flakiness where there is none. A broken assertion then reads
# like an infrastructure blip.
#
# ``OSError`` covers the socket/DNS/connection-reset family, and every HTTP client's
# transport errors subclass either it or its own base, which callers pass explicitly
# (e.g. ``retry_on=(httpx.HTTPError,)``). Widen at the call site, never here.
DEFAULT_RETRY_ON: tuple[type[Exception], ...] = (OSError, TimeoutError)


class WaitTimeout(AssertionError):
    """Raised when a condition never became true within the timeout.

    Subclasses ``AssertionError`` on purpose: a store that never caught up is a test
    failure to report, not an infrastructure error to crash the run with.
    """


def wait_until(
    condition: Callable[[], bool],
    *,
    timeout: float = 60.0,
    interval: float = 2.0,
    description: str = "condition",
) -> None:
    """Poll ``condition`` until it returns True or ``timeout`` elapses.

    ``condition`` is always evaluated at least once, even with a zero timeout, so a
    state that is already correct never fails.

    Args:
        condition: Zero-argument callable returning True when the wait is satisfied.
            Exceptions raised by it propagate immediately — a broken query is a bug,
            not something to wait out.
        timeout: Maximum seconds to keep polling. Source these from
            ``Config.timeout("eventual_consistency")`` rather than a literal.
        interval: Seconds between attempts.
        description: Human-readable name of what's being waited for, used in the
            timeout message and the debug log.

    Returns:
        None.

    Raises:
        WaitTimeout: If ``condition`` never returned True within ``timeout``.
    """
    deadline = time.monotonic() + timeout
    attempt = 0
    while True:
        attempt += 1
        if condition():
            logger.debug("Wait for %s satisfied on attempt %d", description, attempt)
            return
        if time.monotonic() >= deadline:
            raise WaitTimeout(
                f"Timed out after {timeout}s waiting for {description} " f"({attempt} attempts)."
            )
        time.sleep(interval)


def wait_for_value(
    supplier: Callable[[], T | None],
    *,
    timeout: float = 60.0,
    interval: float = 2.0,
    description: str = "value",
) -> T:
    """Poll ``supplier`` until it returns a non-None value; return it.

    The value-returning counterpart to :func:`wait_until`, for the common case of
    "wait for the row to appear, then assert on it" — so callers don't query twice.

    Args:
        supplier: Zero-argument callable returning the value, or None while it isn't
            available yet. Exceptions propagate immediately.
        timeout: Maximum seconds to keep polling.
        interval: Seconds between attempts.
        description: Human-readable name of the value, used in the timeout message.

    Returns:
        The first non-None value ``supplier`` produced.

    Raises:
        WaitTimeout: If ``supplier`` only ever returned None within ``timeout``.
    """
    deadline = time.monotonic() + timeout
    attempt = 0
    while True:
        attempt += 1
        value = supplier()
        if value is not None:
            logger.debug("Wait for %s satisfied on attempt %d", description, attempt)
            return value
        if time.monotonic() >= deadline:
            raise WaitTimeout(
                f"Timed out after {timeout}s waiting for {description} " f"({attempt} attempts)."
            )
        time.sleep(interval)


def retry(
    func: Callable[[], T],
    *,
    attempts: int = DEFAULT_ATTEMPTS,
    delay: float = DEFAULT_DELAY_SECONDS,
    backoff: float = DEFAULT_BACKOFF,
    retry_on: tuple[type[Exception], ...] = DEFAULT_RETRY_ON,
    description: str = "",
) -> T:
    """Call ``func``, retrying on the given exception types with exponential backoff.

    Args:
        func: Zero-argument callable to invoke.
        attempts: Total number of calls, including the first. ``1`` disables retrying.
        delay: Seconds to sleep before the second attempt.
        backoff: Multiplier applied to ``delay`` after each failed attempt.
        retry_on: Exception types treated as transient. Defaults to
            :data:`DEFAULT_RETRY_ON`; anything else propagates on the first occurrence, so
            a real assertion failure is never retried. Widen it here, not in the default.
        description: Name used in the retry log line. Defaults to ``func.__name__``,
            which is useless when ``func`` is a lambda closing over the real call — so
            wrappers pass the underlying operation's name here instead.

    Returns:
        Whatever ``func`` returned on its first successful call.

    Raises:
        ValueError: If ``attempts`` is less than 1 — that would skip the call entirely and
            silently turn "run this" into "never ran".
        Exception: The exception from the final attempt, if every attempt failed.
    """
    if attempts < 1:
        raise ValueError(f"attempts must be >= 1, got {attempts}")
    label = description or getattr(func, "__name__", repr(func))
    current_delay = delay
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except retry_on as exc:
            if attempt == attempts:
                raise
            logger.warning(
                "Attempt %d/%d of %s failed (%s: %s); retrying in %.1fs",
                attempt,
                attempts,
                label,
                type(exc).__name__,
                exc,
                current_delay,
            )
            time.sleep(current_delay)
            current_delay *= backoff
    raise AssertionError(  # pragma: no cover - guarded by the attempts check above
        "unreachable: retry loop exited without returning or raising"
    )


def retry_on_transient_error(
    max_attempts: int = DEFAULT_ATTEMPTS,
    *,
    delay: float = DEFAULT_DELAY_SECONDS,
    backoff: float = DEFAULT_BACKOFF,
    retry_on: tuple[type[Exception], ...] = DEFAULT_RETRY_ON,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator form of :func:`retry`, for BE calls and eventually-consistent DB checks.

    Why a decorator as well as a function: the retry policy belongs to the operation,
    not to each call site. Declaring it once above ``be.run`` keeps every caller —
    this module's orchestrator, another module using it as a precondition, an e2e
    sequence — on the same policy without repeating it.

    Works on both ``def`` and ``async def`` functions; the async form awaits and sleeps
    with ``asyncio.sleep`` so it never blocks the orchestrator's fan-out.

    Args:
        max_attempts: Total number of calls, including the first.
        delay: Seconds before the second attempt.
        backoff: Multiplier applied to ``delay`` after each failed attempt.
        retry_on: Exception types treated as transient. Defaults to
            :data:`DEFAULT_RETRY_ON`; anything else propagates immediately, so a genuine
            assertion failure is reported once instead of being retried into looking flaky.

    Returns:
        A decorator preserving the wrapped function's name, docstring and sync/async
        nature.

    Raises:
        ValueError: If ``max_attempts`` is less than 1 — raised at decoration time, so a
            typo fails at import rather than silently never calling the function.
    """
    if max_attempts < 1:
        raise ValueError(f"max_attempts must be >= 1, got {max_attempts}")

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                current_delay = delay
                for attempt in range(1, max_attempts + 1):
                    try:
                        return await func(*args, **kwargs)
                    except retry_on as exc:
                        if attempt == max_attempts:
                            raise
                        logger.warning(
                            "Attempt %d/%d of %s failed (%s: %s); retrying in %.1fs",
                            attempt,
                            max_attempts,
                            func.__name__,
                            type(exc).__name__,
                            exc,
                            current_delay,
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                raise AssertionError(f"unreachable: max_attempts={max_attempts} must be >= 1")

            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            return retry(
                lambda: func(*args, **kwargs),
                attempts=max_attempts,
                delay=delay,
                backoff=backoff,
                retry_on=retry_on,
                description=func.__name__,
            )

        return sync_wrapper

    return decorator
