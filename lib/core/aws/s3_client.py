"""S3 client wrapper. Read-only by convention — QA verifies objects, does not write them.

PLACEHOLDER — signatures only. Credentials and bucket come from ``get_config().aws``.
"""

from __future__ import annotations

from typing import Any


class S3Client:
    def __init__(self, bucket: str | None = None, region: str | None = None) -> None:
        """Build a client. Defaults come from ``get_config().aws``."""
        raise NotImplementedError("TODO: implement boto3 client setup")

    # --- object checks ---

    def object_exists(self, key: str) -> bool:
        """HEAD the object. Used by eventual-consistency polls."""
        raise NotImplementedError("TODO: implement object_exists")

    def list_objects(self, prefix: str, *, max_keys: int = 1000) -> list[dict[str, Any]]:
        """List objects under a prefix (key, size, last_modified, etag)."""
        raise NotImplementedError("TODO: implement list_objects")

    def get_metadata(self, key: str) -> dict[str, Any]:
        """Object metadata: size, content type, last modified, user metadata."""
        raise NotImplementedError("TODO: implement get_metadata")

    # --- content ---

    def read_bytes(self, key: str) -> bytes:
        raise NotImplementedError("TODO: implement read_bytes")

    def read_text(self, key: str, encoding: str = "utf-8") -> str:
        raise NotImplementedError("TODO: implement read_text")

    def read_json(self, key: str) -> Any:
        raise NotImplementedError("TODO: implement read_json")

    def download(self, key: str, dest: str) -> str:
        """Download to a local path (use a tmp_path fixture as dest). Returns the path."""
        raise NotImplementedError("TODO: implement download")

    def health_check(self) -> bool:
        """Confirm the bucket is reachable — used by fixtures to fail fast."""
        raise NotImplementedError("TODO: implement bucket health check")
