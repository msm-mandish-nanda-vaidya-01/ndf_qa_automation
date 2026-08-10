"""ETL / GDB — module orchestrator.

Sequences the module contract:

    be.py (act) -> fe.py (validate against BE result) -> db/* (verify persisted state)

This file holds the pytest entrypoints. ``be``/``fe``/``db`` hold no test functions
of their own, so ``e2e`` and ``critical_path`` can import and re-sequence them freely.

PLACEHOLDER — test bodies to be filled in.
"""

from __future__ import annotations

import pytest

from lib.app.modules.etl.gdb import be, fe
from lib.app.modules.etl.gdb.db import (
    mongo_checks,
    opensearch_checks,
    postgres_checks,
    s3_checks,
)

MODULE_PATH = "etl/gdb"


@pytest.fixture(scope="module")
def etl_case(test_data):
    """Load the GDB ETL payload for the active env/subsidiary/data set."""
    raise NotImplementedError("TODO: load the case file from test_data(MODULE_PATH)")


@pytest.fixture(scope="module")
def be_result(etl_client, etl_case):
    """Run the BE action once per module; every downstream check validates against it."""
    raise NotImplementedError("TODO: return be.run(etl_client, etl_case)")


@pytest.mark.module
@pytest.mark.be
def test_be_etl_completes(be_result):
    """The ETL job reaches a successful terminal state."""
    raise NotImplementedError("TODO: assert on be_result status/record_count")


@pytest.mark.module
@pytest.mark.fe
def test_fe_matches_be(logged_in_page, config, be_result):
    """The UI reflects exactly what the BE reported."""
    raise NotImplementedError("TODO: call fe.validate(logged_in_page, config, be_result)")


@pytest.mark.module
@pytest.mark.db
@pytest.mark.postgres
def test_postgres_state(postgres, config, be_result):
    """Postgres holds the persisted job + records."""
    raise NotImplementedError("TODO: call postgres_checks.verify(postgres, config, be_result)")


@pytest.mark.module
@pytest.mark.db
@pytest.mark.mongo
def test_mongo_state(mongo, config, be_result):
    """Mongo holds the persisted documents."""
    raise NotImplementedError("TODO: call mongo_checks.verify(mongo, config, be_result)")


@pytest.mark.module
@pytest.mark.db
@pytest.mark.opensearch
def test_opensearch_state(opensearch, config, be_result):
    """The ETL output is indexed and searchable."""
    raise NotImplementedError("TODO: call opensearch_checks.verify(opensearch, config, be_result)")


@pytest.mark.module
@pytest.mark.db
@pytest.mark.s3
def test_s3_state(s3, config, be_result):
    """The ETL output object landed in S3."""
    raise NotImplementedError("TODO: call s3_checks.verify(s3, config, be_result)")


# --- reusable sequence for e2e / critical_path ---


def run_full_flow(*, etl_client, page, config, stores, case) -> be.GdbEtlResult:
    """Run act -> validate -> verify as one callable and return the BE result.

    This is what ``e2e/orchestrator.py`` and ``critical_path/orchestrator.py`` call;
    they do not duplicate the sequence.
    """
    raise NotImplementedError("TODO: compose be.run -> fe.validate -> the four db verifies")
