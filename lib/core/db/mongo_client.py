"""MongoDB client wrapper. Read-only by convention.

PLACEHOLDER — signatures only. Connection details come from ``get_config().mongo``.
When ``get_config().mongo.tls_ca_file`` is set (DocumentDB, in ``stg``/``prod``), pass
``tls=True, tlsCAFile=tls_ca_file`` to the pymongo client — see certs/README.md for
where that file comes from. When ``get_config().aws.bastion_host`` is set, this client
connects through the SSH tunnel opened by the ``_bastion_tunnel`` fixture in
``lib/core/fixtures/db_fixtures.py``, not directly to ``uri``'s host.
"""

from __future__ import annotations

from typing import Any


class MongoDBClient:
    def __init__(self, uri: str | None = None, database: str | None = None) -> None:
        """Build a client. Defaults come from ``get_config().mongo``."""
        raise NotImplementedError("TODO: implement pymongo client setup")

    # --- lifecycle ---

    def close(self) -> None:
        raise NotImplementedError("TODO: close client")

    def __enter__(self) -> MongoDBClient:
        raise NotImplementedError("TODO: context-manager entry")

    def __exit__(self, *exc_info: object) -> None:
        raise NotImplementedError("TODO: context-manager exit")

    # --- queries ---

    def find_one(self, collection: str, query: dict[str, Any]) -> dict[str, Any] | None:
        raise NotImplementedError("TODO: implement find_one")

    def find(
        self,
        collection: str,
        query: dict[str, Any],
        *,
        projection: dict[str, Any] | None = None,
        sort: list[tuple[str, int]] | None = None,
        limit: int = 0,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError("TODO: implement find")

    def count_documents(self, collection: str, query: dict[str, Any]) -> int:
        raise NotImplementedError("TODO: implement count_documents")

    def exists(self, collection: str, query: dict[str, Any]) -> bool:
        """Used by eventual-consistency polls."""
        raise NotImplementedError("TODO: implement exists")

    def aggregate(self, collection: str, pipeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
        raise NotImplementedError("TODO: implement aggregate")

    def list_collections(self) -> list[str]:
        raise NotImplementedError("TODO: implement list_collections")

    def health_check(self) -> bool:
        """``ping`` command."""
        raise NotImplementedError("TODO: implement health check")
