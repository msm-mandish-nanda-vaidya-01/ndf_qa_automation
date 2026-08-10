"""ETL / GDB — MongoDB persisted-state verification.

PLACEHOLDER — signatures only. Fill in once the GDB collections are confirmed.
"""

from __future__ import annotations

from lib.app.modules.etl.gdb.be import GdbEtlResult

# --- collections: fill in with the real names ---
JOB_COLLECTION = "etl_gdb_jobs"  # TODO: confirm collection name
DOCUMENT_COLLECTION = "etl_gdb_documents"  # TODO: confirm collection name


def assert_job_document_exists(client, be_result: GdbEtlResult) -> dict:
    """A job document exists for ``be_result.job_id``. Returns it."""
    raise NotImplementedError("TODO: find_one by job_id, poll for eventual consistency")


def assert_document_count(client, be_result: GdbEtlResult) -> None:
    """Persisted document count equals ``be_result.record_count``."""
    raise NotImplementedError("TODO: count_documents for this job")


def assert_document_shape(client, be_result: GdbEtlResult) -> None:
    """Persisted documents carry the required fields with the right types."""
    raise NotImplementedError("TODO: assert required keys/types on a sample of documents")


def assert_subsidiary_scoping(client, config, be_result: GdbEtlResult) -> None:
    """Documents are scoped to the active subsidiary."""
    raise NotImplementedError("TODO: assert subsidiary field matches config.subsidiary")


def verify(client, config, be_result: GdbEtlResult) -> None:
    """Entrypoint: all Mongo checks for this module."""
    raise NotImplementedError("TODO: compose the assertions above")
