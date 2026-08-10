"""ETL / GDB — Postgres persisted-state verification.

Asserts what is actually stored, not what the BE response echoed back.

PLACEHOLDER — signatures only. Fill in once the GDB schema is confirmed.
"""

from __future__ import annotations

from lib.app.modules.etl.gdb.be import GdbEtlResult

# --- schema: fill in with the real table/column names ---
JOB_TABLE = "etl_gdb_job"  # TODO: confirm table name
RECORD_TABLE = "etl_gdb_record"  # TODO: confirm table name


def assert_job_row_exists(client, be_result: GdbEtlResult) -> dict:
    """A job row exists for ``be_result.job_id``. Returns the row."""
    raise NotImplementedError("TODO: query JOB_TABLE by job_id, poll for eventual consistency")


def assert_job_status(client, be_result: GdbEtlResult) -> None:
    """The persisted status equals the status the BE reported."""
    raise NotImplementedError("TODO: compare the stored status column against be_result.status")


def assert_record_count(client, be_result: GdbEtlResult) -> None:
    """The number of persisted records equals ``be_result.record_count``."""
    raise NotImplementedError("TODO: COUNT(*) on RECORD_TABLE for this job")


def assert_subsidiary_scoping(client, config, be_result: GdbEtlResult) -> None:
    """No rows leaked across subsidiaries — everything is scoped to the active one."""
    raise NotImplementedError("TODO: assert every row's subsidiary matches config.subsidiary")


def assert_no_orphans(client, be_result: GdbEtlResult) -> None:
    """Every record row references a live job row."""
    raise NotImplementedError("TODO: assert there are no orphaned record rows")


def verify(client, config, be_result: GdbEtlResult) -> None:
    """Entrypoint: all Postgres checks for this module."""
    raise NotImplementedError("TODO: compose the assertions above")
