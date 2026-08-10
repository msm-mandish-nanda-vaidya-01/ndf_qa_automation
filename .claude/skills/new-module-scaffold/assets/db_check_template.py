"""<DB_TYPE> checks for the <MODULE_NAME> module.

Context:
    Verifies <DB_TYPE> state that <MODULE_NAME> is responsible for persisting. Only checks
    this module's own data — do not verify state another module owns, even if it's convenient
    to check here; put that in the owning module's db check instead.

    Delete this file if <MODULE_NAME> doesn't touch <DB_TYPE>.

    Source of the expected value (see docs/context/test-data-conventions.md, "Where the
    'expected result' comes from"): prefer `be_result` whenever this module's `be.py` produced
    the state under test in the same run. Fall back to a test-data-defined expected value
    (`test_case.expected`, hardcoded or resolved from <DB_TYPE>/backend by this module's own
    code) only when there's no live `be_result` to compare against — e.g. a pure validation
    check with no corresponding action. State which mode this module uses below once decided;
    don't leave both paths half-wired.
"""

import logging

from lib.core.db import <db_client_module>  # e.g. postgres_client, mongo_client, opensearch_client
from lib.core.utils import wait_helper

logger = logging.getLogger(__name__)


@wait_helper.retry_on_transient_error(max_attempts=3)  # keep for eventually-consistent stores
async def verify(test_case, be_result: dict | None) -> dict:
    """Verify <DB_TYPE> reflects the expected state for this test case.

    Args:
        test_case: Parsed test case, used to identify which record(s)/document(s)/index
            entries to look up, and to supply `test_case.expected` when this module has no
            live `be_result` to compare against.
        be_result: The dict returned by be.py for this same test case, or None if this module
            has no be.py / no be_result applies to this check.

    Returns:
        A dict with the actual query/lookup result, for reporting even on success.

    Raises:
        AssertionError: If persisted state doesn't match the expected value (from be_result or
            from test_case, whichever this module uses).
    """
    client = <db_client_module>.get_client()
    logger.debug("DB[<DB_TYPE>] lookup for %s", test_case.name)

    # actual = await client.fetch(...)
    actual = {}

    # Pick ONE of these two — don't leave both:
    # expected = expected_from(be_result)          # live BE result is source of truth
    # expected = expected_from(test_case.expected)  # hardcoded or DB/backend-resolved in test data

    # assert actual == expected, (
    #     f"<DB_TYPE> mismatch for {test_case.name}: expected {expected!r}, got {actual!r}"
    # )

    logger.debug("DB[<DB_TYPE>] result: %s", actual)
    return actual
