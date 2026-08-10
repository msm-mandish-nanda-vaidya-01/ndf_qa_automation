"""ETL / GDB — OpenSearch index verification.

Indexing lags the write, so every check here polls rather than asserting once.

PLACEHOLDER — signatures only. Fill in once the GDB index mapping is confirmed.
"""

from __future__ import annotations

from lib.app.modules.etl.gdb.be import GdbEtlResult

# --- index: fill in with the real name/alias ---
GDB_INDEX = "etl-gdb"  # TODO: confirm index or alias name


def assert_index_exists(client) -> None:
    """The target index/alias exists in the cluster."""
    raise NotImplementedError("TODO: assert index_exists(GDB_INDEX)")


def assert_documents_indexed(client, be_result: GdbEtlResult) -> None:
    """The ETL output is searchable; hit count equals ``be_result.record_count``."""
    raise NotImplementedError("TODO: poll count until it matches, honoring the refresh timeout")


def assert_document_searchable_by_job(client, be_result: GdbEtlResult) -> dict:
    """A document is retrievable by ``be_result.job_id``. Returns the first hit."""
    raise NotImplementedError("TODO: search by job_id and return the first _source")


def assert_field_mapping(client, be_result: GdbEtlResult) -> None:
    """Indexed fields match the expected mapping types — catches silent mapping drift."""
    raise NotImplementedError("TODO: compare the live mapping against the expected one")


def verify(client, config, be_result: GdbEtlResult) -> None:
    """Entrypoint: all OpenSearch checks for this module.

    Skips when ``features.verify_opensearch`` is off.
    """
    raise NotImplementedError("TODO: compose the assertions above, gated on the feature flag")
