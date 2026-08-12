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
    """
    raise NotImplementedError(
        "TODO: delegate to lib.app.modules.purchase_checker.login.fe.open_login_page + "
        "submit_credentials, then return the page"
    )


@pytest.fixture(scope="session")
def storage_state(browser, config):
    """Reusable auth state so not every test pays the login cost.

    Same rule as ``logged_in_page``: drive the login through
    ``purchase_checker/login``'s ``fe.py``, then save ``context.storage_state()``.
    """
    raise NotImplementedError(
        "TODO: log in once via purchase_checker/login's fe.py, save storage_state, "
        "return the path"
    )
