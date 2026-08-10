"""URL construction and comparison helpers.

PLACEHOLDER — signatures only. Fill in when the FE/BE route map is confirmed.
"""

from __future__ import annotations


def join(base: str, *parts: str) -> str:
    """Join a base URL with path segments, collapsing duplicate slashes."""
    raise NotImplementedError("TODO: implement URL join")


def with_query(url: str, **params: object) -> str:
    """Append/replace query-string parameters on ``url``."""
    raise NotImplementedError("TODO: implement query-param builder")


def normalize(url: str) -> str:
    """Canonical form for comparison: lowercase host, no trailing slash, sorted query."""
    raise NotImplementedError("TODO: implement URL normalization")


def same_page(actual: str, expected: str, *, ignore_query: bool = False) -> bool:
    """True when two URLs point at the same page. Used by FE assertions."""
    raise NotImplementedError("TODO: implement URL comparison")


def path_of(url: str) -> str:
    """Return just the path component."""
    raise NotImplementedError("TODO: implement path extraction")
