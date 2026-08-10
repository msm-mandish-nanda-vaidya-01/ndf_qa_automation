"""Polling helpers for eventual consistency.

The BE action returns before downstream stores have caught up, so DB/S3/OpenSearch
checks poll instead of asserting once.

PLACEHOLDER — signatures only.
"""

from __future__ import annotations

from typing import Callable, TypeVar

T = TypeVar("T")


class WaitTimeout(AssertionError):
    """Raised when a condition never became true within the timeout."""


def wait_until(
    condition: Callable[[], bool],
    *,
    timeout: float = 60.0,
    interval: float = 2.0,
    description: str = "condition",
) -> None:
    """Poll ``condition`` until it returns True or ``timeout`` elapses."""
    raise NotImplementedError("TODO: implement polling loop")


def wait_for_value(
    supplier: Callable[[], T | None],
    *,
    timeout: float = 60.0,
    interval: float = 2.0,
    description: str = "value",
) -> T:
    """Poll ``supplier`` until it returns a non-None value; return it."""
    raise NotImplementedError("TODO: implement value polling")


def retry(
    func: Callable[[], T],
    *,
    attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    retry_on: tuple[type[Exception], ...] = (Exception,),
) -> T:
    """Call ``func``, retrying on the given exception types with exponential backoff."""
    raise NotImplementedError("TODO: implement retry with backoff")
