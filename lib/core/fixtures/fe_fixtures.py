"""Frontend fixtures: browser, context, page, authenticated session.

PLACEHOLDER — fixture bodies to be filled in.
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session")
def browser(config):
    """Launch the browser once per session, honoring ``features.fe_headless``."""
    raise NotImplementedError("TODO: launch playwright browser from config.settings['browser']")


@pytest.fixture
def context(browser, config):
    """Fresh, isolated browser context per test. Starts tracing when enabled."""
    raise NotImplementedError("TODO: new_context with viewport + optional tracing")


@pytest.fixture
def page(context, config, request):
    """A page with default timeouts applied.

    On failure, capture a screenshot and trace when the corresponding feature
    flags are on, and attach them to the Allure report.

    Capturing "on failure" needs the test outcome, which pytest does not expose to
    fixtures directly — it requires a ``pytest_runtest_makereport`` hookwrapper stashing
    each phase's report on the item. That hook used to live in ``conftest.py`` and was
    removed because nothing read it; **reinstate it together with this fixture**, not
    before. For a working example of failure-artifact capture today, see
    ``purchase_checker/login``'s orchestrator, which owns its own contexts and so needs
    no hook.
    """
    raise NotImplementedError("TODO: new_page, set timeouts, capture artifacts on failure")


@pytest.fixture
def logged_in_page(page, config):
    """A page already authenticated as ``credentials.fe_username``.

    Do NOT reimplement the login interaction here. ``purchase_checker/login``'s
    ``fe.py`` owns the selectors and the click sequence, and duplicating them is the
    failure mode CLAUDE.md calls out as the most common mistake in this codebase — the
    two copies drift the moment the login page changes.

    Call its one cross-module entry point, ``fe.log_in(page, config)``, which submits the
    form *and* waits for the authenticated page. Not ``open_login_page`` +
    ``submit_credentials``: that pair returns mid-submit, so anything read afterwards sees
    the page as it was before the server answered. Not ``fe.assert_matches`` either — that
    asserts a login *scenario* and would report the login module's outcomes inside whatever
    test requested this fixture.
    """
    raise NotImplementedError(
        "TODO: await lib.app.modules.purchase_checker.login.fe.log_in(page, config), "
        "then return the page"
    )


@pytest.fixture(scope="session")
def storage_state(browser, config):
    """Reusable auth state so not every test pays the login cost.

    Same rule as ``logged_in_page``: log in once through
    ``purchase_checker/login``'s ``fe.log_in``, then save ``context.storage_state()`` and
    seed later contexts with it (verified: a fresh context built from that state is already
    authenticated).
    """
    raise NotImplementedError(
        "TODO: log in once via purchase_checker/login's fe.log_in, save storage_state, "
        "return the path"
    )
