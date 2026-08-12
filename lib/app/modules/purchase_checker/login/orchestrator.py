"""Purchase Checker / Login — module orchestrator.

Sequences the module contract:

    be.py (act) -> fe.py (validate against BE result)

There is no ``db/*`` layer for this module — see ``PLAN.md`` §2 — because the
XDB Cross data-layer wiring is still unconfirmed (docs/context/module-workflows.md,
"Known gaps"). An absent file is the signal, not an oversight.

This file is also the concurrency boundary: it fans the module's test-data files out in
parallel and owns the single browser instance those flows share, so a run opens one
browser rather than one per test case.

Two entry points on purpose:

* :func:`run` — the async, data-driven entry point every module exposes, callable from
  the CLI.
* ``test_login_module`` — a thin pytest wrapper so ``make test-login``, ``pytest.ini``
  and CI reach the same flow. It exists because ``pytest.ini`` configures no
  ``asyncio_mode``; wrapping with ``asyncio.run`` avoids adding a dependency just to
  bridge the two.

Failure policy, all three parts of it:

* **No short-circuit.** The FE layer runs even when the BE layer failed, per
  ``system-flow.md``. A layer that genuinely cannot run is recorded in the result's
  ``skipped`` list, never as a second entry in ``errors``.
* **No batch loss.** One case's unforeseen failure must not discard the others, so the
  fan-out gathers with ``return_exceptions=True`` and artifact capture is independently
  guarded. Teardown is bounded as well as guarded (``_close_quietly``): a browser that
  never finishes closing must not swallow a run whose results are already computed.
* **No silent pass.** A run that resolves zero test cases raises rather than reporting
  success.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest
from playwright.async_api import Browser, async_playwright

from lib.app.modules.purchase_checker.login import be, fe
from lib.core.config.env_config import REPORTS_ROOT, Config, get_config
from lib.core.utils import data_loader, report_generator

logger = logging.getLogger(__name__)

MODULE_PATH = "purchase_checker/login"


class NoTestCasesError(RuntimeError):
    """Raised when a run resolved zero test cases.

    Exists because the alternative is worse than a failure: ``data_loader`` only warns on
    an empty directory, so without this a renamed or unauthored test-data folder produces
    a green run that executed nothing.
    """


# Playwright context cap, per docs/context/system-flow.md. Raise only if the app under
# test is known to tolerate more — each context is a real browser session against a
# shared environment.
MAX_CONCURRENT_TEST_CASES = 5

# Upper bound on each Playwright teardown call. `close()` waits for the browser to
# acknowledge and exit, and a wedged Chromium simply never answers — observed here as a
# run that logged "FE: finished" and then sat in `browser.close()` until pytest's 300s
# timeout killed it, reporting a hang instead of the result it had already computed.
# Abandoning a close is safe: leaving `async_playwright`'s context stops the driver, which
# reaps the browser process anyway.
CLOSE_TIMEOUT_SECONDS = 30


async def _run_test_case(
    test_case: Any, env: str, subsidiary_cd: str, browser: Browser, config: Config
) -> dict[str, Any]:
    """Run the full be -> fe flow for a single test case.

    Every layer runs even if an earlier one failed, so the report carries what the BE
    returned *and* what the UI showed rather than only the first failure. When the BE
    produced no result, the FE still runs against a synthesised stand-in carrying just the
    login id — the scenario that most needs an independent browser-level check (a
    credential that authenticated when it should not have) is precisely the one where the
    BE layer raises.

    Args:
        test_case: A parsed test case from ``data_loader``.
        env: One of "dev", "stg", "prod".
        subsidiary_cd: One of settings.yaml's ``defaults.subsidiaries``.
        browser: The shared Playwright browser; this function opens its own isolated
            context so concurrent cases never share cookies.
        config: The resolved run configuration.

    Returns:
        A result dict with ``test_case``, ``errors`` and ``skipped`` keys, plus ``be`` and
        ``fe`` when those layers produced a result. ``errors`` is empty when the case
        passed. A layer that could not run is recorded in ``skipped``, not ``errors``, so
        a skip never renders as a second failure.
    """
    result: dict[str, Any] = {"test_case": test_case.name, "errors": [], "skipped": []}
    be_result: be.LoginResult | None = None

    logger.info("BE: starting %s", test_case.name)
    try:
        be_result = await be.run(test_case, env, subsidiary_cd)
        result["be"] = be_result.to_report_dict()
        logger.info("BE: finished %s", test_case.name)
    except Exception as exc:
        logger.error("BE failed for %s: %s", test_case.name, exc)
        result["errors"].append({"stage": "be", "error": str(exc)})

    # Some scenarios are not expressible through the UI at all — a `country` override, for
    # instance, is a form field the BE sets directly, whereas the browser always submits
    # the country belonging to the locale page it is on. Running the FE for those would
    # silently perform an ordinary valid login and report a false failure. Such a case
    # declares itself BE-only and is recorded as skipped, not failed.
    if not test_case.get("fe_applicable", True):
        reason = "scenario is not expressible through the UI (declared fe_applicable=false)"
        logger.info("FE: skipping %s — %s", test_case.name, reason)
        result["skipped"].append({"stage": "fe", "reason": reason})
        return result

    # The FE layer runs even when the BE failed — system-flow.md's no-short-circuit rule,
    # and the case that most needs an independent browser-level check (a credential that
    # authenticated when it should not have) is exactly the one where BE raises. All the
    # FE needs from the BE is the login id, which is recoverable from the test case.
    logger.info("FE: starting %s", test_case.name)
    fe_expected = (
        be_result
        if be_result is not None
        else _synthesize_be_result(test_case, env, subsidiary_cd, config)
    )
    context = None
    page = None
    tracing = False
    try:
        context = await browser.new_context(viewport=config.settings["browser"]["viewport"])
        # Tracing has to be started before the actions it records, so a trace-on-failure
        # policy necessarily traces the passing cases too. Measured over 15 samples that
        # costs nothing detectable here — the dominant cost in this block is Chromium
        # serialising new_page across concurrent contexts (~0.8s more per additional
        # context), which tracing does not affect.
        tracing = config.feature("fe_trace_on_failure", True)
        if tracing:
            await context.tracing.start(screenshots=True, snapshots=True)
        page = await context.new_page()
        result["fe"] = await fe.assert_matches(page, config, test_case, fe_expected)
        logger.info("FE: finished %s", test_case.name)
        if tracing:
            # Discard the trace of a passing case explicitly rather than leaving it to
            # context.close(). With MAX_CONCURRENT_TEST_CASES contexts each buffering
            # screenshots and DOM snapshots, freeing the buffer at the earliest point
            # keeps peak memory flat as the batch grows.
            await _stop_tracing(context, test_case.name, path=None)
    except Exception as exc:
        logger.error("FE failed for %s: %s", test_case.name, exc)
        result["errors"].append({"stage": "fe", "error": str(exc)})
        await _capture_failure_artifacts(page, context, test_case.name, config, tracing)
    finally:
        # Capture before close, and never let teardown or artifact capture escape: an
        # exception here would propagate into asyncio.gather and discard every other
        # test case's result, and a close that hangs would stall the batch behind the
        # semaphore. _close_quietly handles both.
        if context is not None:
            await _close_quietly(context, f"context for {test_case.name}")

    return result


def _synthesize_be_result(
    test_case: Any, env: str, subsidiary_cd: str, config: Config
) -> be.LoginResult:
    """Build the minimal ``LoginResult`` the FE layer needs when the BE produced none.

    Why: ``fe.assert_matches`` consumes only ``login_id`` on the rejection path (the cookie
    fields are read solely on the success path), and that id is derivable from the test case
    and config. Synthesising it lets the FE layer still run after a BE failure instead of
    being skipped — without pretending a session was issued.

    Args:
        test_case: The parsed test case; supplies a ``login_id`` override if present.
        env: One of "dev", "stg", "prod". Recorded for context only.
        subsidiary_cd: The subsidiary being exercised.
        config: The resolved run configuration; supplies the fallback login id.

    Returns:
        A :class:`be.LoginResult` with ``succeeded=False`` and no token, carrying only the
        login id the FE should submit.
    """
    login_id = test_case.get("login_id")
    return be.LoginResult(
        subsidiary_cd=subsidiary_cd,
        login_id=config.credentials.fe_username if login_id is None else login_id,
        succeeded=False,
    )


async def _close_quietly(closable: Any, what: str) -> None:
    """Close a Playwright context or browser without letting teardown break the run.

    Guards the two ways a close can go wrong. An *exception* is a non-event: the thing
    being closed is already gone, and re-raising from a ``finally`` would replace the real
    test result or escape into ``asyncio.gather`` and discard the whole batch. A *hang* is
    the more damaging one, because there is no exception to swallow — `close()` waits on
    the browser process, and a wedged Chromium never answers, so an unbounded await
    consumes pytest's whole session timeout and the run reports a timeout instead of the
    results it had already finished computing.

    Bounded rather than retried: a close that hasn't returned in
    ``CLOSE_TIMEOUT_SECONDS`` will not return at all, and leaving ``async_playwright``'s
    context stops the driver, which reaps the process regardless. This is deliberately not
    ``wait_helper``'s retry — CLAUDE.md scopes that to eventually-consistent BE and DB
    calls, not to teardown, where a second attempt has nothing new to wait for.

    Args:
        closable: A Playwright ``BrowserContext`` or ``Browser``.
        what: Label for the log line, e.g. ``"browser"`` or ``"context for S1_valid_login"``.

    Returns:
        None. Never raises — a timeout is logged at WARNING (abnormal, but no test case
        failed), any other error at DEBUG.
    """
    try:
        await asyncio.wait_for(closable.close(), timeout=CLOSE_TIMEOUT_SECONDS)
    except TimeoutError:
        logger.warning(
            "Timed out after %ss closing %s; abandoning it — the Playwright driver will "
            "reap the process on shutdown. Results are unaffected.",
            CLOSE_TIMEOUT_SECONDS,
            what,
        )
    except Exception as exc:  # noqa: BLE001 - teardown must not fail the batch
        logger.debug("Could not close %s: %s", what, exc)


async def _stop_tracing(context: Any, case_name: str, path: str | None) -> None:
    """Stop a context's Playwright trace, optionally writing it to ``path``.

    Args:
        context: The Playwright context currently tracing.
        case_name: Test-case name, for the debug log.
        path: Destination for the trace archive, or None to discard it — which is what a
            passing case wants.

    Returns:
        None. Failures are logged at DEBUG and swallowed; a trace is a diagnostic, and
        losing one must never affect the test result or the batch.
    """
    try:
        await context.tracing.stop(path=path) if path else await context.tracing.stop()
    except Exception as exc:  # noqa: BLE001 - diagnostics must not fail a run
        logger.debug("Could not stop tracing for %s: %s", case_name, exc)


async def _capture_failure_artifacts(
    page: Any, context: Any, case_name: str, config: Config, tracing: bool
) -> None:
    """Attach a screenshot, the page URL and a Playwright trace for a failed FE check.

    Why this is its own function with its own guard: the usual cause of an FE failure is a
    page or context that has died, in which case ``screenshot()`` itself raises. Awaited
    inline in the caller's ``except`` block that exception would replace the real failure,
    escape into ``asyncio.gather`` and destroy the whole batch — losing the diagnostic it
    was trying to capture. Reporting must never fail a run.

    Args:
        page: The Playwright page, or None if it was never created.
        context: The Playwright context, or None if it was never created.
        case_name: Test-case name, used in the attachment titles.
        config: The resolved run configuration; supplies the feature flags and the run
            target used to name the trace file uniquely.
        tracing: Whether tracing was actually started for this context. Passed in rather
            than re-read from the feature flag because the context may have failed before
            tracing began, and stopping a trace that never started raises.

    Returns:
        None. Every failure inside is logged at DEBUG and swallowed.
    """
    if page is not None and config.feature("fe_screenshot_on_failure", True):
        try:
            report_generator.attach_screenshot(
                f"FE failure screenshot: {case_name}", await page.screenshot(full_page=True)
            )
            report_generator.attach_text(f"FE failure page URL: {case_name}", page.url)
        except Exception as exc:  # noqa: BLE001 - see docstring
            logger.debug("Could not capture FE screenshot for %s: %s", case_name, exc)

    if context is not None and tracing:
        # Name the archive per env/subsidiary as well as case: pytest-xdist can run two
        # subsidiaries concurrently against the same repo, and their case names are
        # identical, so a case-only name would have them overwrite each other.
        trace_path = (
            REPORTS_ROOT
            / "traces"
            / f"{config.env}_{config.subsidiary}_{config.data_set}_{case_name}.zip"
        )
        try:
            trace_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:  # noqa: BLE001 - see docstring
            logger.debug("Could not create the traces directory: %s", exc)
            return
        await _stop_tracing(context, case_name, str(trace_path))
        if trace_path.exists():
            report_generator.attach_text(
                f"FE failure trace: {case_name}",
                f"Playwright trace written to {trace_path}\n"
                f"View with: playwright show-trace {trace_path}",
            )


async def run(env: str, subsidiary_cd: str, kind: str | None = None) -> list[dict[str, Any]]:
    """Run every login test case for this env/subsidiary, in parallel.

    Args:
        env: One of "dev", "stg", "prod".
        subsidiary_cd: One of settings.yaml's ``defaults.subsidiaries``, e.g. ``"MJP"``.
        kind: "real" or "test" — which test-data folder to load from. ``None`` (the
            default) falls through to the run's ``DATA_SET``, matching
            ``data_loader.load``. A hardcoded default here would silently override the
            environment for direct callers.

    Returns:
        One result dict per test case, each containing the redacted BE result, the FE
        result (when it ran) and any errors encountered — full context regardless of
        whether the case ultimately failed.

    Raises:
        ConfigError: If the env/subsidiary is unknown or the test-data directory for this
            module doesn't exist.
        NoTestCasesError: If the resolved directory contains no case files. A run that
            executes nothing must not report success — a green suite that tested nothing
            is worse than a red one.

        Per-test-case failures do not raise; they are folded into that case's result so
        one bad case doesn't kill the batch.
    """
    config = get_config(env=env, subsidiary=subsidiary_cd, data_set=kind)
    resolved_kind = kind if kind is not None else config.data_set
    test_cases = data_loader.load(MODULE_PATH, env, subsidiary_cd, resolved_kind)
    logger.info(
        "Starting %d test case(s) for %s (%s/%s/%s)",
        len(test_cases),
        MODULE_PATH,
        env,
        subsidiary_cd,
        resolved_kind,
    )
    if not test_cases:
        raise NoTestCasesError(
            f"No test-data case files for {MODULE_PATH} in "
            f"{config.test_data_dir(MODULE_PATH)}. A run with zero test cases would "
            "report success without testing anything."
        )

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TEST_CASES)

    async with async_playwright() as playwright:
        browser = await playwright[config.settings["browser"]["name"]].launch(
            headless=config.feature("fe_headless", True),
            slow_mo=config.settings["browser"].get("slow_mo_ms", 0),
        )
        try:

            async def _run_one(test_case: Any) -> dict[str, Any]:
                async with semaphore:
                    return await _run_test_case(test_case, env, subsidiary_cd, browser, config)

            # return_exceptions so an unforeseen escape from _run_test_case costs that one
            # case rather than every case's results — see _capture_failure_artifacts.
            raw = await asyncio.gather(
                *(_run_one(case) for case in test_cases), return_exceptions=True
            )
        finally:
            await _close_quietly(browser, "browser")

    results = [_as_result(case, outcome) for case, outcome in zip(test_cases, raw, strict=True)]
    report_generator.attach_module_results(module=MODULE_PATH, results=results)
    return results


def _as_result(test_case: Any, outcome: dict[str, Any] | BaseException) -> dict[str, Any]:
    """Normalise one ``asyncio.gather`` outcome into a result dict.

    With ``return_exceptions=True`` an entry is either the result dict ``_run_test_case``
    built, or the exception that escaped it. This converts the latter into the same shape
    so the report and the pytest wrapper have one thing to consume.

    Args:
        test_case: The case this outcome belongs to, for naming.
        outcome: The gathered value — a result dict, or an exception.

    Returns:
        A result dict. An escaped exception is recorded under the ``orchestrator`` stage,
        which distinguishes "the harness broke" from "a layer's assertion failed".
    """
    if isinstance(outcome, BaseException):
        logger.error(
            "Unhandled error running %s: %s: %s",
            test_case.name,
            type(outcome).__name__,
            outcome,
        )
        return {
            "test_case": test_case.name,
            "errors": [{"stage": "orchestrator", "error": f"{type(outcome).__name__}: {outcome}"}],
            "skipped": [],
        }
    return outcome


# --- pytest entry point ---


@pytest.mark.module
@pytest.mark.be
@pytest.mark.fe
def test_login_module(config: Config) -> None:
    """Every login scenario passes its BE action and its FE validation.

    Thin wrapper over :func:`run` so the module is reachable from ``pytest``,
    ``make test-login`` and CI. Reports every failing case at once rather than stopping
    at the first, matching the orchestrator's no-short-circuit contract.

    Args:
        config: Session fixture carrying the run's env/subsidiary/data set.

    Returns:
        None.

    Raises:
        AssertionError: If any test case recorded an error in any layer, or if the run
            resolved no test cases at all (surfaced from ``NoTestCasesError`` — a run that
            executed nothing is reported as a failure, never as a pass).
    """
    try:
        results = asyncio.run(run(config.env, config.subsidiary, config.data_set))
    except NoTestCasesError as exc:
        pytest.fail(str(exc), pytrace=False)

    for result in results:
        for skip in result.get("skipped", []):
            logger.warning(
                "%s: %s skipped — %s", result["test_case"], skip["stage"], skip["reason"]
            )

    failures = [result for result in results if result["errors"]]
    if failures:
        summary = "\n".join(
            f"  {result['test_case']}: "
            + "; ".join(f"{e['stage']}: {e['error']}" for e in result["errors"])
            for result in failures
        )
        pytest.fail(
            f"{len(failures)}/{len(results)} login test case(s) failed:\n{summary}",
            pytrace=False,
        )
