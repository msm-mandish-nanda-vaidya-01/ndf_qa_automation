"""FE assertions for the <MODULE_NAME> module.

Context:
    Drives the relevant Admin Panel page via Playwright and asserts the UI reflects the state
    that be.py already produced. Delete this file entirely if <MODULE_NAME> has nothing to
    check in the UI — don't leave an empty stub.

    Source of the expected value: prefer `be_result` (see docs/context/test-data-conventions.md).
    Only assert against `test_case.expected` instead when this module genuinely has no live
    be_result for the field being checked.
"""

import logging

from playwright.async_api import Page

from lib.core.utils import wait_helper

logger = logging.getLogger(__name__)


async def assert_matches(page: Page, test_case, be_result: dict) -> dict:
    """Assert the Admin Panel page reflects what be_result says should be true.

    Args:
        page: An authenticated Playwright page, already navigated to (or about to navigate to)
            the relevant Admin Panel screen.
        test_case: Parsed test case, used for navigation params (e.g. which record to open).
        be_result: The dict returned by be.py for this same test case — assert against this,
            not against a hardcoded expectation.

    Returns:
        A dict capturing what was observed on the page, for reporting even on success.

    Raises:
        AssertionError: If the UI doesn't match be_result.
    """
    logger.info("FE: navigating for %s", test_case.name)
    # await page.goto(url_helper.build(..., path=f"/admin/records/{be_result['id']}"))
    # await page.wait_for_selector("selector-for-relevant-field")

    observed = {}  # e.g. {"status_label": await page.text_content("selector")}
    logger.debug("FE observed: %s", observed)

    # assert observed["status_label"] == be_result["expected_status"], (
    #     f"UI showed {observed['status_label']!r}, BE said {be_result['expected_status']!r}"
    # )

    return observed
