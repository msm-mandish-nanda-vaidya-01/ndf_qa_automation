"""OpenSearch client wrapper. Read-only by convention.

Indexing lags writes — pair searches with ``wait_helper.wait_until`` rather than
asserting immediately after the BE action.

PLACEHOLDER — signatures only. Connection details come from ``get_config().opensearch``.
"""

from __future__ import annotations

from typing import Any


class OpenSearchClient:
    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        *,
        use_ssl: bool | None = None,
    ) -> None:
        """Build a client. Defaults come from ``get_config().opensearch``."""
        raise NotImplementedError("TODO: implement opensearch-py client setup")

    # --- lifecycle ---

    def close(self) -> None:
        raise NotImplementedError("TODO: close client")

    def __enter__(self) -> OpenSearchClient:
        raise NotImplementedError("TODO: context-manager entry")

    def __exit__(self, *exc_info: object) -> None:
        raise NotImplementedError("TODO: context-manager exit")

    # --- queries ---

    def search(
        self,
        index: str,
        query: dict[str, Any],
        *,
        size: int = 10,
        sort: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Raw search — returns the full response body."""
        raise NotImplementedError("TODO: implement search")

    def hits(self, index: str, query: dict[str, Any], *, size: int = 10) -> list[dict[str, Any]]:
        """Search and return just the ``_source`` documents."""
        raise NotImplementedError("TODO: implement hits extraction")

    def get_document(self, index: str, doc_id: str) -> dict[str, Any] | None:
        raise NotImplementedError("TODO: implement get by id")

    def count(self, index: str, query: dict[str, Any] | None = None) -> int:
        raise NotImplementedError("TODO: implement count")

    def exists(self, index: str, query: dict[str, Any]) -> bool:
        """Used by eventual-consistency polls."""
        raise NotImplementedError("TODO: implement exists")

    def index_exists(self, index: str) -> bool:
        raise NotImplementedError("TODO: implement index existence check")

    def refresh(self, index: str) -> None:
        """Force an index refresh so freshly-written docs become searchable."""
        raise NotImplementedError("TODO: implement refresh")

    def health_check(self) -> bool:
        """Cluster health — used by fixtures to fail fast."""
        raise NotImplementedError("TODO: implement health check")
