"""Critical-path orchestrator — smoke level, gates deploys.

A subset of the module units: the fastest path that still proves the system is
usable. It skips exhaustive assertions but still verifies persisted state where a
silent write failure would be unacceptable.

Target runtime: a few minutes. This is what CI runs on every PR.

PLACEHOLDER — test bodies to be filled in.
"""

from __future__ import annotations

import pytest

from lib.app.modules.etl.gdb import be as gdb_be
from lib.app.modules.etl.gdb import fe as gdb_fe
from lib.app.modules.etl.gdb.db import postgres_checks as gdb_postgres
from lib.app.modules.etl.gdb.db import s3_checks as gdb_s3
from lib.app.modules.purchase_checker.login import be as login_be
from lib.app.modules.purchase_checker.login import fe as login_fe
from lib.app.modules.purchase_checker.login.db import postgres_checks as login_postgres

pytestmark = pytest.mark.critical_path


@pytest.fixture(scope="module")
def smoke_session(purchase_checker_client, config):
    """Single login reused across the critical path."""
    raise NotImplementedError("TODO: return login_be.run(purchase_checker_client, ...)")


def test_service_reachability(config, stores):
    """FE, BE and every datastore respond before anything else is attempted.

    Fails fast and loudly on a broken environment so downstream failures are not
    misread as product bugs.
    """
    raise NotImplementedError("TODO: hit FE/BE health endpoints and each client's health_check")


def test_login_works(smoke_session, page, config, postgres):
    """A user can log in, the UI shows them as logged in, and the session is persisted."""
    raise NotImplementedError(
        "TODO: login_fe.assert_logged_in_as + login_postgres.assert_session_row_created"
    )


def test_gdb_etl_completes_and_persists(smoke_session, etl_client, config, postgres, s3, test_data):
    """A minimal ETL run completes and its output reaches Postgres and S3.

    Uses the smallest case in the module's test data — not the full dataset.
    """
    raise NotImplementedError(
        "TODO: gdb_be.run on the smoke case, then gdb_postgres/gdb_s3 spot checks"
    )


def test_key_screens_render(smoke_session, page, config):
    """Each critical screen loads without error for an authenticated user."""
    raise NotImplementedError("TODO: visit the critical routes and assert no error state")
