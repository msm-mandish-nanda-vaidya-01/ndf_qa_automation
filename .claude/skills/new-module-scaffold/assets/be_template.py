"""BE actions for the <MODULE_NAME> module.

Context:
    Hits <MODULE_NAME>'s endpoint(s) via httpx and returns the resulting response/state. This
    is the source of truth that fe.py and db/*_checks.py validate against — do not hardcode
    expected values elsewhere that duplicate what this function already returns.
"""

import logging

import httpx

from lib.core.utils import url_helper, wait_helper

logger = logging.getLogger(__name__)


@wait_helper.retry_on_transient_error(max_attempts=3)
async def run(test_case, env: str, subsidiary_cd: str) -> dict:
    """Perform <MODULE_NAME>'s action against the real endpoint for one test case.

    Args:
        test_case: Parsed test case (fields depend on this module's own test-data schema —
            document that schema here once it's finalized).
        env: One of "dev", "stg", "prod".
        subsidiary_cd: One of "MJP", "KOR", "USA".

    Returns:
        The parsed response body / resulting state, in whatever shape fe.py and the db/*
        checks need to compare against.

    Raises:
        httpx.HTTPStatusError: If the endpoint returns a non-2xx status after retries.
        httpx.TimeoutException: If the endpoint doesn't respond after retries.
    """
    url = url_helper.build(env=env, subsidiary_cd=subsidiary_cd, path="/replace/with/endpoint")
    logger.debug("BE request: %s payload=%s", url, test_case.payload)

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=test_case.payload)
        response.raise_for_status()

    body = response.json()
    logger.debug("BE response: %s", body)
    return body
