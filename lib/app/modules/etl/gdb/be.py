"""ETL / GDB — backend layer. Performs the action and returns the resulting state.

This is the only layer that *acts*. ``fe.py`` and ``db/*`` consume what it returns;
neither re-derives expected values independently.

PLACEHOLDER — signatures only. Fill in once the GDB ETL endpoints are confirmed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GdbEtlResult:
    """What the BE action produced. The contract passed to ``fe.py`` and ``db/*``.

    Fill in the real fields as the endpoint contract firms up.
    """

    job_id: str = ""
    status: str = ""
    record_count: int = 0
    subsidiary: str = ""
    submitted_at: str = ""  # ISO8601, as returned by the BE
    s3_output_key: str = ""  # object the ETL wrote — consumed by s3_checks
    raw_response: dict[str, Any] = field(default_factory=dict)


def trigger_etl(client, payload: dict[str, Any]) -> GdbEtlResult:
    """POST the ETL trigger and return the parsed result.

    Asserts only on the transport contract (status code, response shape) — business
    assertions belong in ``fe.py`` and ``db/*``.
    """
    raise NotImplementedError("TODO: call the GDB ETL trigger endpoint")


def wait_for_completion(client, job_id: str, *, timeout: float = 300.0) -> GdbEtlResult:
    """Poll the job-status endpoint until the ETL job reaches a terminal state."""
    raise NotImplementedError("TODO: poll job status until terminal")


def get_job(client, job_id: str) -> GdbEtlResult:
    """Fetch a single job's current state."""
    raise NotImplementedError("TODO: GET the job-status endpoint")


def run(client, payload: dict[str, Any]) -> GdbEtlResult:
    """Module entrypoint: trigger, wait, return the final result.

    Called by this module's orchestrator and reused by ``e2e`` / ``critical_path``.
    """
    raise NotImplementedError("TODO: compose trigger_etl + wait_for_completion")
