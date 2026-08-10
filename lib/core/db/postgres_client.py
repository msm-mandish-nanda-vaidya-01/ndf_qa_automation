"""Postgres client wrapper. Read-only by convention — QA verifies, it does not mutate.

PLACEHOLDER — signatures only. Connection details come from
``get_config().postgres``; never hardcode credentials here.
"""

from __future__ import annotations

from typing import Any, Sequence


class PostgresClient:
    def __init__(self, dsn: str | None = None) -> None:
        """Build a client. ``dsn`` defaults to ``get_config().postgres.dsn``."""
        raise NotImplementedError("TODO: implement psycopg connection setup")

    # --- lifecycle ---

    def connect(self) -> None:
        raise NotImplementedError("TODO: open connection / pool")

    def close(self) -> None:
        raise NotImplementedError("TODO: close connection / pool")

    def __enter__(self) -> PostgresClient:
        raise NotImplementedError("TODO: context-manager entry")

    def __exit__(self, *exc_info: object) -> None:
        raise NotImplementedError("TODO: context-manager exit")

    # --- queries ---

    def fetch_all(self, sql: str, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
        """Run a SELECT and return all rows as dicts."""
        raise NotImplementedError("TODO: implement fetch_all")

    def fetch_one(self, sql: str, params: Sequence[Any] | None = None) -> dict[str, Any] | None:
        """Run a SELECT and return the first row, or None."""
        raise NotImplementedError("TODO: implement fetch_one")

    def fetch_value(self, sql: str, params: Sequence[Any] | None = None) -> Any:
        """Run a SELECT and return the first column of the first row."""
        raise NotImplementedError("TODO: implement fetch_value")

    def count(self, table: str, where: str = "", params: Sequence[Any] | None = None) -> int:
        """Row count for a table with an optional WHERE clause."""
        raise NotImplementedError("TODO: implement count")

    def exists(self, sql: str, params: Sequence[Any] | None = None) -> bool:
        """True when the query returns at least one row. Used by eventual-consistency polls."""
        raise NotImplementedError("TODO: implement exists")

    def health_check(self) -> bool:
        """``SELECT 1`` — used by fixtures to fail fast on a bad environment."""
        raise NotImplementedError("TODO: implement health check")
