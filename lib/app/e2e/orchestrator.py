"""End-to-end orchestrator — cross-module sequences.

Imports ``be``/``fe``/``db`` from the module packages and only decides *which* units
run and in what order. It defines no new BE actions, FE assertions or DB queries;
if something is missing here, it belongs in the owning module.

PLACEHOLDER — test bodies to be filled in.
"""

from __future__ import annotations

import pytest

from lib.app.modules.etl.gdb import be as gdb_be
from lib.app.modules.etl.gdb import fe as gdb_fe
from lib.app.modules.etl.gdb.db import mongo_checks as gdb_mongo
from lib.app.modules.etl.gdb.db import opensearch_checks as gdb_opensearch
from lib.app.modules.etl.gdb.db import postgres_checks as gdb_postgres
from lib.app.modules.etl.gdb.db import s3_checks as gdb_s3
from lib.app.modules.purchase_checker.login import be as login_be
from lib.app.modules.purchase_checker.login import fe as login_fe
from lib.app.modules.purchase_checker.login.db import mongo_checks as login_mongo
from lib.app.modules.purchase_checker.login.db import opensearch_checks as login_opensearch
from lib.app.modules.purchase_checker.login.db import postgres_checks as login_postgres
from lib.app.modules.purchase_checker.login.db import s3_checks as login_s3

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def e2e_session(purchase_checker_client, config):
    """Authenticate once; every downstream step in the flow reuses this session."""
    raise NotImplementedError("TODO: return login_be.run(purchase_checker_client, ...)")


def test_login_then_gdb_etl_full_flow(
    e2e_session,
    purchase_checker_client,
    etl_client,
    page,
    config,
    stores,
    test_data,
):
    """Full chain: log in -> validate UI -> verify session state -> run GDB ETL ->
    validate UI against the ETL result -> verify persisted state in all four stores.

    Sequence to implement:
      1. login_fe.validate(page, config, e2e_session)
      2. login_postgres/mongo/opensearch/s3.verify(..., e2e_session)
      3. etl_result = gdb_be.run(etl_client, case)
      4. gdb_fe.validate(page, config, etl_result)
      5. gdb_postgres/mongo/opensearch/s3.verify(..., etl_result)
    """
    raise NotImplementedError("TODO: implement the cross-module sequence")


def test_etl_output_visible_to_logged_in_user(
    e2e_session, etl_client, page, config, stores, test_data
):
    """Data produced by the ETL is visible to the authenticated user in the UI,
    and the permission set from login gates what that user can see."""
    raise NotImplementedError("TODO: implement the cross-module visibility check")


def test_session_expiry_blocks_etl_access(e2e_session, purchase_checker_client, etl_client, config):
    """After logout the ETL endpoints reject the stale session — cross-module authz."""
    raise NotImplementedError("TODO: logout, then assert ETL access is refused")
