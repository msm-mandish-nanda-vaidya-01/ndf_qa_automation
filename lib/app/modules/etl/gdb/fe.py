"""ETL / GDB — frontend layer. Asserts the UI reflects the BE result.

Every function takes the ``GdbEtlResult`` from ``be.py`` as input. Expected values
come from that result — never re-queried, never hardcoded.

PLACEHOLDER — signatures only. Fill in once the GDB screens/locators are confirmed.
"""

from __future__ import annotations

from lib.app.modules.etl.gdb.be import GdbEtlResult

# --- locators: fill in with the real selectors ---
JOB_TABLE = "[data-testid='gdb-job-table']"  # TODO: confirm selector
JOB_ROW = "[data-testid='gdb-job-row']"  # TODO: confirm selector
JOB_STATUS_BADGE = "[data-testid='gdb-job-status']"  # TODO: confirm selector
RECORD_COUNT = "[data-testid='gdb-record-count']"  # TODO: confirm selector


def open_job_list(page, config) -> None:
    """Navigate to the GDB ETL job list and wait for it to render."""
    raise NotImplementedError("TODO: navigate to the job list page")


def open_job_detail(page, config, job_id: str) -> None:
    """Navigate to a single job's detail view."""
    raise NotImplementedError("TODO: navigate to the job detail page")


def assert_job_visible(page, be_result: GdbEtlResult) -> None:
    """The job produced by the BE appears in the UI list."""
    raise NotImplementedError("TODO: assert the row for be_result.job_id is present")


def assert_status_matches(page, be_result: GdbEtlResult) -> None:
    """The status shown in the UI equals the status the BE reported."""
    raise NotImplementedError("TODO: compare the badge text against be_result.status")


def assert_record_count_matches(page, be_result: GdbEtlResult) -> None:
    """The record count shown in the UI equals ``be_result.record_count``."""
    raise NotImplementedError("TODO: compare the displayed count against be_result.record_count")


def validate(page, config, be_result: GdbEtlResult) -> None:
    """Module entrypoint: full FE validation of a BE result.

    Called by this module's orchestrator and reused by ``e2e`` / ``critical_path``.
    """
    raise NotImplementedError("TODO: compose the assertions above")
