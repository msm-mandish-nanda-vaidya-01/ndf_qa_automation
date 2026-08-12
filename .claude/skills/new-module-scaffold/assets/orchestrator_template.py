"""Orchestrator for the <MODULE_NAME> module.

Context:
    Defines the test flow for <MODULE_NAME>: for each test case, calls `be.py` to perform the
    action against the real endpoint, then (if present) `fe.py` to assert the Admin Panel
    reflects that result, then every `db/*_checks.py` present for this module to verify
    persisted state. Also owns the concurrency fan-out across test-data files (data-driven
    approach) — see docs/context/system-flow.md.

    Delete the fe/db calls below if this module doesn't use those layers. Do not leave stub
    calls to files that don't exist.
"""

import asyncio
import logging

from lib.core.utils import data_loader, report_generator

# from lib.app.modules.<domain>.<module_name> import be, fe
# from lib.app.modules.<domain>.<module_name>.db import postgres_checks, mongo_checks, opensearch_checks, s3_checks

# If this module depends on another module's state, import that module's LAYERS separately
# and call only their state-establishing entry points — never its assertions, db/* or
# orchestrator (see system-flow.md, "Cross-module dependencies"):
#   from lib.app.modules.<dependency_domain>.<dependency_module> import be as dependency_be
#   from lib.app.modules.<dependency_domain>.<dependency_module> import fe as dependency_fe
# The BE half returns values this module carries forward (e.g. auth headers); the FE half
# leaves `page` authenticated so this module keeps navigating in that session. Import only
# the half this module needs.

logger = logging.getLogger(__name__)

MAX_CONCURRENT_TEST_CASES = 5  # Playwright context cap — tune per module, see system-flow.md


async def run(env: str, subsidiary_cd: str, kind: str = "test") -> list[dict]:
    """Run every test case for <MODULE_NAME> in this env/subsidiary, in parallel.

    Args:
        env: One of "dev", "stg", "prod".
        subsidiary_cd: One of "MJP", "KOR", "USA".
        kind: "real" or "test" — which test-data folder to load from.

    Returns:
        One result dict per test case, each containing the BE result, FE result (if run),
        every DB check result that ran, and any exceptions encountered — full context
        regardless of whether the test case ultimately failed.

    Raises:
        Nothing here directly; per-test-case exceptions are caught and folded into that
        test case's result so one bad test case doesn't kill the batch.
    """
    test_cases = list(data_loader.load("<domain>/<module_name>", env, subsidiary_cd, kind))
    logger.info(
        "Starting %s test cases for <MODULE_NAME> (%s/%s/%s)",
        len(test_cases), env, subsidiary_cd, kind,
    )

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TEST_CASES)

    async def _run_one(test_case) -> dict:
        async with semaphore:
            return await _run_test_case(test_case, env, subsidiary_cd)

    results = await asyncio.gather(*(_run_one(tc) for tc in test_cases))
    report_generator.attach_module_results(module="<MODULE_NAME>", results=results)
    return results


async def _run_test_case(test_case, env: str, subsidiary_cd: str) -> dict:
    """Run the full be -> fe -> db flow for a single test case.

    Context:
        Every confirmed layer runs even if an earlier layer fails, so the failure report has
        full context. Only a precondition/dependency failure short-circuits this function.

    Args:
        test_case: A parsed test case object from data_loader.
        env: One of "dev", "stg", "prod".
        subsidiary_cd: One of "MJP", "KOR", "USA".

    Returns:
        A result dict with keys among {"be", "fe", "db", "errors"} depending on which layers
        this module uses.
    """
    result: dict = {"test_case": test_case.name, "errors": []}

    # --- Precondition / cross-module dependency (delete if not applicable) ---
    # Both halves, or just the one this module needs. Wrapped together because either
    # failing means the same thing: the precondition isn't in place, so there is nothing
    # meaningful left to check for this test case.
    # try:
    #     # BE half — state to pass forward into this module's own requests.
    #     precondition_state = await dependency_be.login(env, subsidiary_cd)
    #     auth_headers = precondition_state.auth_headers()
    #     # FE half — leaves `page` authenticated; this module continues in that session.
    #     # Reuse page.context.storage_state() across test cases rather than logging in
    #     # once per case (see system-flow.md, "Cross-module dependencies").
    #     await dependency_fe.log_in(page, config)
    # except Exception as exc:
    #     logger.error("Precondition failed for %s: %s", test_case.name, exc)
    #     result["errors"].append({"stage": "precondition", "error": str(exc)})
    #     return result  # nothing meaningful left to check

    # --- BE ---
    try:
        logger.info("BE: starting %s", test_case.name)
        # result["be"] = await be.run(test_case, env, subsidiary_cd)
        logger.info("BE: finished %s", test_case.name)
    except Exception as exc:
        logger.error("BE failed for %s: %s", test_case.name, exc)
        result["errors"].append({"stage": "be", "error": str(exc)})

    # --- FE (delete this block if this module has no fe.py) ---
    try:
        logger.info("FE: starting %s", test_case.name)
        # result["fe"] = await fe.assert_matches(test_case, result.get("be"))
        logger.info("FE: finished %s", test_case.name)
    except Exception as exc:
        logger.error("FE failed for %s: %s", test_case.name, exc)
        result["errors"].append({"stage": "fe", "error": str(exc)})

    # --- DB (delete blocks for checks this module doesn't use) ---
    result["db"] = {}
    for name, _check_fn in [
        # ("postgres", postgres_checks.verify),
        # ("mongo", mongo_checks.verify),
        # ("opensearch", opensearch_checks.verify),
        # ("s3", s3_checks.verify),
    ]:
        try:
            logger.info("DB[%s]: starting %s", name, test_case.name)
            # result["db"][name] = await _check_fn(test_case, result.get("be"))
            logger.info("DB[%s]: finished %s", name, test_case.name)
        except Exception as exc:
            logger.error("DB[%s] failed for %s: %s", name, test_case.name, exc)
            result["errors"].append({"stage": f"db.{name}", "error": str(exc)})

    return result
