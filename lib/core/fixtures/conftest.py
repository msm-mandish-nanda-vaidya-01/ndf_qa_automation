"""Root fixture registration.

Loaded as a pytest plugin via ``-p lib.core.fixtures.conftest`` in pytest.ini, so
these fixtures are available to every module without duplicating conftest files.

PLACEHOLDER — fixture bodies to be filled in.
"""

from __future__ import annotations

import pytest

pytest_plugins = [
    "lib.core.fixtures.fe_fixtures",
    "lib.core.fixtures.be_fixtures",
    "lib.core.fixtures.db_fixtures",
]


# --- CLI options: let a run target an env/subsidiary/data set without editing .env ---


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register ``--env``, ``--subsidiary``, ``--data-set``."""
    raise NotImplementedError("TODO: add options, defaulting to the matching env vars")


@pytest.fixture(scope="session")
def config():
    """Resolved run configuration (``lib.core.config.env_config.Config``)."""
    raise NotImplementedError("TODO: build via get_config(), overridden by CLI options")


@pytest.fixture(scope="session", autouse=True)
def _logging(config):
    """Initialize logging once per session and stamp Allure run metadata."""
    raise NotImplementedError("TODO: call setup_logging() and write_run_metadata()")


@pytest.fixture(scope="session")
def test_data(config):
    """Callable: ``test_data("etl/gdb")`` -> that module's resolved test-data directory."""
    raise NotImplementedError("TODO: return a closure over config.test_data_dir")


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    """Expose the test result to fixtures so FE teardown can capture on failure."""
    raise NotImplementedError("TODO: stash the report on item for fe fixtures")
