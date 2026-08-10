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
    """
    raise NotImplementedError("TODO: new_page, set timeouts, capture artifacts on failure")


@pytest.fixture
def logged_in_page(page, config):
    """A page already authenticated as ``credentials.fe_username``."""
    raise NotImplementedError("TODO: perform login and return the page")


@pytest.fixture(scope="session")
def storage_state(browser, config):
    """Reusable auth state so not every test pays the login cost."""
    raise NotImplementedError("TODO: log in once, save storage_state, return the path")
