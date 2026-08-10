"""ETL / GDB — S3 output verification.

PLACEHOLDER — signatures only. Fill in once the GDB output key layout is confirmed.
"""

from __future__ import annotations

from lib.app.modules.etl.gdb.be import GdbEtlResult

# --- key layout: fill in with the real prefix pattern ---
OUTPUT_PREFIX = "etl/gdb/{env}/{subsidiary}/{job_id}/"  # TODO: confirm prefix pattern


def expected_prefix(config, be_result: GdbEtlResult) -> str:
    """Render ``OUTPUT_PREFIX`` for this run."""
    raise NotImplementedError("TODO: format OUTPUT_PREFIX from config + be_result")


def assert_output_object_exists(client, config, be_result: GdbEtlResult) -> None:
    """The object named in ``be_result.s3_output_key`` exists."""
    raise NotImplementedError("TODO: poll object_exists until present")


def assert_object_not_empty(client, be_result: GdbEtlResult) -> None:
    """The output object has non-zero size."""
    raise NotImplementedError("TODO: assert metadata size > 0")


def assert_object_content(client, be_result: GdbEtlResult) -> None:
    """Object contents match ``be_result`` — row count, header, schema."""
    raise NotImplementedError("TODO: read the object and compare against be_result.record_count")


def assert_no_unexpected_objects(client, config, be_result: GdbEtlResult) -> None:
    """Nothing extra was written under the job prefix."""
    raise NotImplementedError("TODO: list the prefix and assert the key set is exactly expected")


def verify(client, config, be_result: GdbEtlResult) -> None:
    """Entrypoint: all S3 checks for this module.

    Skips when ``features.verify_s3`` is off.
    """
    raise NotImplementedError("TODO: compose the assertions above, gated on the feature flag")
