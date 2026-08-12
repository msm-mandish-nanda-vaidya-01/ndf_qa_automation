"""Root fixture registration.

Loaded as a pytest plugin via ``-p lib.core.fixtures.conftest`` in pytest.ini, so
these fixtures are available to every module without duplicating conftest files.

Only the run-wide concerns live here — which env/subsidiary/data set the run targets,
logging, and test-data resolution. Layer-specific clients (browser, HTTP, datastores)
live in the ``fe_fixtures`` / ``be_fixtures`` / ``db_fixtures`` plugins listed below.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import pytest

from lib.core.config.env_config import Config, get_config
from lib.core.config.logging_config import setup_logging
from lib.core.utils.report_generator import (
    AllureCliError,
    generate_report,
    write_run_metadata,
)

pytest_plugins = [
    "lib.core.fixtures.fe_fixtures",
    "lib.core.fixtures.be_fixtures",
    "lib.core.fixtures.db_fixtures",
]


# --- CLI options: let a run target an env/subsidiary/data set without editing .env.<env> ---


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register ``--env``, ``--subsidiary``, ``--data-set``.

    Defaults are ``None`` rather than a literal so an unset option falls through to
    ``get_config``'s own resolution chain (``ENV`` / ``SUBSIDIARY`` / ``DATA_SET``, then
    the documented default). Baking defaults in here would silently override those.

    Args:
        parser: The pytest option parser.

    Returns:
        None.
    """
    group = parser.getgroup("ndf", "NDF QA automation run target")
    group.addoption(
        "--env",
        action="store",
        default=None,
        help="Target environment: dev | stg | prod. Defaults to $ENV, then dev.",
    )
    group.addoption(
        "--subsidiary",
        action="store",
        default=None,
        help=(
            "Subsidiary code, e.g. MJP. Must be listed in settings.yaml's "
            "defaults.subsidiaries. Defaults to $SUBSIDIARY, then the first entry."
        ),
    )
    group.addoption(
        "--data-set",
        action="store",
        default=None,
        choices=("real", "test"),
        help="Which test-data folder to read. Defaults to $DATA_SET, then test.",
    )


@pytest.fixture(scope="session")
def config(request: pytest.FixtureRequest) -> Config:
    """Resolved run configuration (``lib.core.config.env_config.Config``).

    Session-scoped because it is immutable and expensive-ish to build; every fixture and
    module reads the same instance so a run can't half-target two environments.

    Args:
        request: Pytest request, used to read the CLI options.

    Returns:
        The resolved :class:`Config` for this run.

    Raises:
        ConfigError: If the env/subsidiary is unknown, the secrets file is missing
            outside CI, or a configured cert path doesn't exist.
    """
    return get_config(
        env=request.config.getoption("--env"),
        subsidiary=request.config.getoption("--subsidiary"),
        data_set=request.config.getoption("--data-set"),
    )


@pytest.fixture(scope="session", autouse=True)
def _logging(config: Config) -> None:
    """Initialize logging once per session and stamp Allure run metadata.

    Autouse so no module has to remember to request it — an unconfigured logger would
    silently drop the DEBUG payload/query records that make a failure diagnosable.

    The log file is named per run target, per CLAUDE.md's
    ``logs/<suite>_<env>_<subsidiary_cd>_<timestamp>.txt`` convention, so parallel runs
    against different subsidiaries don't interleave into one file.

    The metadata call is retained but self-disabling: ``write_run_metadata`` no-ops while
    ``features.allure_enabled`` is false (the current default), so a run writes its log
    file as always and nothing under ``reports/allure-results``.

    Args:
        config: The resolved run configuration.

    Returns:
        None.
    """
    setup_logging(
        level=logging.INFO,
        log_file=f"run_{config.env}_{config.subsidiary}_{config.data_set}.log",
    )
    write_run_metadata(config.env, config.subsidiary, config.data_set)
    logging.getLogger(__name__).info(
        "Run target: env=%s subsidiary=%s data_set=%s",
        config.env,
        config.subsidiary,
        config.data_set,
    )


@pytest.fixture(scope="session")
def test_data(config: Config) -> Callable[[str], Path]:
    """Callable: ``test_data("etl/gdb")`` -> that module's resolved test-data directory.

    A callable rather than a path because one session can touch several modules (e2e and
    critical-path sequences do), and each needs its own directory resolved from the same
    run target.

    Args:
        config: The resolved run configuration.

    Returns:
        A function mapping a module path to its test-data directory. The returned
        function raises ``ConfigError`` if that directory doesn't exist.
    """

    def resolve(module_path: str) -> Path:
        return config.test_data_dir(module_path)

    return resolve


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Render the Allure HTML site once the whole session has finished.

    Why here rather than in an orchestrator: results accumulate across every module in the
    session, so the site can only be generated once they are all written. ``sessionfinish``
    is the last hook with the results directory complete.

    **Currently a no-op**: ``features.allure_enabled`` is false in settings.yaml, so this
    returns before invoking the Allure commandline. The hook is left wired up so flipping
    that one flag (plus restoring ``--alluredir`` in pytest.ini, which is what makes
    allure-pytest write the raw results this renders) brings reporting back with no code
    change. ``features.auto_generate_allure_report`` remains the narrower switch — keep the
    site generation off while still collecting raw results.

    **Never fails the run.** Generating the site needs the external Allure commandline,
    which isn't installed everywhere. A missing or failing CLI is reported as a WARNING
    naming the manual command — turning a passing suite red over a reporting tool would be
    the wrong trade.

    Args:
        session: The finished pytest session, used to reach the run configuration.
        exitstatus: The session's exit status. Unused — the report is just as useful for
            a failing run, and arguably more so.

    Returns:
        None.
    """
    try:
        config = get_config(
            env=session.config.getoption("--env"),
            subsidiary=session.config.getoption("--subsidiary"),
            data_set=session.config.getoption("--data-set"),
        )
        if not config.feature("allure_enabled", True):
            return
        if not config.feature("auto_generate_allure_report", True):
            return
        generate_report()
    except AllureCliError as exc:
        logging.getLogger(__name__).warning("Allure report not generated: %s", exc)
    except Exception as exc:  # noqa: BLE001 - reporting must never fail the session
        logging.getLogger(__name__).warning(
            "Skipped Allure report generation: %s: %s", type(exc).__name__, exc
        )
