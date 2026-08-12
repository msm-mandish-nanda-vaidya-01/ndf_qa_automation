"""Root fixture registration.

Loaded as a pytest plugin via ``-p lib.core.fixtures.conftest`` in pytest.ini, so
these fixtures are available to every module without duplicating conftest files.

Only the run-wide concerns live here — which env/subsidiary/data set the run targets,
logging, and test-data resolution. Layer-specific clients (browser, HTTP, datastores)
live in the ``fe_fixtures`` / ``be_fixtures`` / ``db_fixtures`` plugins listed below.

**A run targets a matrix, not a single combination.** ``--env`` / ``--subsidiary`` /
``--data-set`` each accept several values (repeat the flag or comma-separate), and an
option left out expands to *every* configured value for that dimension. Every test that
requests the ``config`` fixture is therefore parametrized once per combination, with ids
like ``test_login_module[dev-MJP-test]``, so one command covers the whole matrix and each
combination passes or fails on its own.

Combinations reached only by that expansion are skipped when the module under test has no
test data authored for them — otherwise a bare ``pytest`` would report failures for
env/subsidiary pairs nobody has written cases for yet. A combination named **explicitly**
on the command line is never skipped: asking for something unauthored is an error worth
seeing, per CLAUDE.md's "a run that tested nothing must not report success".
"""

from __future__ import annotations

import itertools
import logging
import os
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

from lib.core.config.env_config import (
    DATA_SETS,
    ENVIRONMENTS,
    Config,
    ConfigError,
    configured_subsidiaries,
    get_config,
)
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


@dataclass(frozen=True)
class RunTarget:
    """One env/subsidiary/data-set combination a run covers.

    Attributes:
        env: One of ``ENVIRONMENTS``.
        subsidiary: One of ``settings.yaml``'s ``defaults.subsidiaries``.
        data_set: One of ``DATA_SETS``.
        expanded: True when at least one of the three was filled in by expanding an
            omitted option rather than named on the command line. Drives skip-vs-fail for
            combinations with no test data: exploring the matrix may legitimately reach
            unauthored ground, asking for it by name may not.
    """

    env: str
    subsidiary: str
    data_set: str
    expanded: bool

    @property
    def id(self) -> str:
        """Return the pytest parameter id, e.g. ``"dev-MJP-test"``."""
        return f"{self.env}-{self.subsidiary}-{self.data_set}"


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the repeatable ``--env``, ``--subsidiary`` and ``--data-set`` options.

    Each is ``append``-style and additionally splits on commas, so ``--env dev --env stg``
    and ``--env dev,stg`` mean the same thing. ``default=None`` distinguishes "not given"
    (expand to every configured value) from any explicit list — an omitted option is a
    request for full coverage, not a fallback to one default combination.

    Values are validated in :func:`resolve_run_targets` rather than by argparse
    ``choices``, which cannot express a comma-separated list, and which would reject the
    case-insensitive spellings (``DEV``, ``mjp``) accepted here.

    Args:
        parser: The pytest option parser.

    Returns:
        None.
    """
    group = parser.getgroup("ndf", "NDF QA automation run target")
    group.addoption(
        "--env",
        action="append",
        default=None,
        metavar="ENV",
        help=(
            f"Target environment(s): {' | '.join(ENVIRONMENTS)}. Repeatable and "
            "comma-separated (--env dev,stg). Omitted: every environment."
        ),
    )
    group.addoption(
        "--subsidiary",
        action="append",
        default=None,
        metavar="CODE",
        help=(
            "Subsidiary code(s), e.g. MJP. Must be listed in settings.yaml's "
            "defaults.subsidiaries. Repeatable and comma-separated. Omitted: every "
            "configured subsidiary."
        ),
    )
    group.addoption(
        "--data-set",
        action="append",
        default=None,
        metavar="KIND",
        help=(
            f"Which test-data folder(s) to read: {' | '.join(DATA_SETS)}. Repeatable and "
            "comma-separated. Omitted: both."
        ),
    )


def _requested(pytest_config: pytest.Config, option: str, variable: str) -> list[str] | None:
    """Flatten one repeatable option into a list of values.

    Falls back to the matching **process** environment variable when the flag is absent,
    so ``ENV=stg make test`` and CI — which passes the run target as ``ENV`` /
    ``SUBSIDIARY`` / ``DATA_SET`` rather than as flags — still select a target instead of
    silently running the whole matrix. The variable accepts the same comma-separated form
    as the flag (``ENV=dev,stg``).

    Deliberately **not** read from ``.env.<env>``, even though ``get_config`` layers that
    file under the process environment for every other key. Those files set ``ENV`` and
    ``DATA_SET`` as per-environment configuration, not as a statement about which
    environments a run should cover; honouring ``DATA_SET=test`` from ``.env.dev`` here
    would mean a bare ``pytest`` never ran the ``real`` data set, which is exactly the
    full-coverage default this indirection exists to provide.

    Args:
        pytest_config: The pytest config holding the parsed options.
        option: Option name, e.g. ``"--env"``.
        variable: Environment variable consulted when the option is absent, e.g. ``"ENV"``.

    Returns:
        The values given, with comma-separated entries split apart and blanks dropped, or
        None when neither the option nor the variable was set — the signal to expand to
        every configured value. A source present but empty (``--env ""``) returns an empty
        list, which :func:`_resolve_dimension` rejects rather than silently treating as
        "all".
    """
    raw: Sequence[str] | None = pytest_config.getoption(option)
    if raw is None:
        from_environment = os.environ.get(variable)
        if from_environment is None:
            return None
        raw = [from_environment]
    return [piece.strip() for value in raw for piece in value.split(",") if piece.strip()]


def _resolve_dimension(
    requested: list[str] | None, allowed: Iterable[str], label: str, *, upper: bool = False
) -> tuple[list[str], bool]:
    """Validate one dimension's values, or expand it to everything configured.

    Args:
        requested: Values from the command line, or None when the option was omitted.
        allowed: Every configured value for this dimension, in authored order.
        label: Option name for error messages, e.g. ``"--env"``.
        upper: Uppercase the input before matching (subsidiary codes) instead of
            lowercasing it (environments, data sets). Either way the comparison is
            case-insensitive, so ``--env DEV`` and ``--subsidiary mjp`` both work.

    Returns:
        A ``(values, expanded)`` pair. ``expanded`` is True when the option was omitted
        and the full list was substituted. Duplicates are collapsed and the configured
        order is preserved, so ``--env stg,dev,stg`` runs dev then stg exactly once.

    Raises:
        pytest.UsageError: If a value is not one of ``allowed``, or the option was given
            with no usable value. Raised as a usage error so the CLI prints one clear
            line instead of a collection traceback.
    """
    allowed = list(allowed)
    if requested is None:
        return allowed, True
    normalized = [value.upper() if upper else value.lower() for value in requested]
    unknown = [value for value in normalized if value not in allowed]
    if unknown or not normalized:
        raise pytest.UsageError(
            f"Unknown {label} value(s): {', '.join(unknown) or '<empty>'}. "
            f"Configured: {', '.join(allowed)}"
        )
    return [value for value in allowed if value in normalized], False


def pytest_configure(config: pytest.Config) -> None:
    """Validate the run-target options before collection starts.

    Resolving the matrix here as well as during collection is deliberate, not redundant:
    a :class:`pytest.UsageError` raised from ``pytest_generate_tests`` surfaces as a
    collection error wrapped in a traceback, while the same error raised here prints as a
    single ``ERROR:`` line. A typo in ``--env`` is the likeliest mistake at this CLI, and
    it should read like a usage message rather than a crash. The result is discarded —
    ``resolve_run_targets`` is pure and cheap.

    The parameter is named ``config`` because pluggy matches hook arguments to the
    hookspec by name; it is the pytest ``Config`` object, unrelated to this module's
    ``config`` *fixture*, which is a resolved :class:`Config` for one combination.

    Args:
        config: The pytest config holding the parsed options.

    Returns:
        None.

    Raises:
        pytest.UsageError: If any of the three options names something unconfigured.
    """
    resolve_run_targets(config)


def resolve_run_targets(pytest_config: pytest.Config) -> list[RunTarget]:
    """Build the full list of combinations this run covers.

    The cartesian product of the three dimensions, each either as given on the command
    line or expanded to every configured value. Ordered env-major so a run walks one
    environment at a time, which keeps a matrix run's log readable.

    Args:
        pytest_config: The pytest config holding the parsed options.

    Returns:
        One :class:`RunTarget` per combination; never empty.

    Raises:
        pytest.UsageError: If any option names something unconfigured.
        ConfigError: If ``settings.yaml`` has no subsidiary list.
    """
    envs, envs_expanded = _resolve_dimension(
        _requested(pytest_config, "--env", "ENV"), ENVIRONMENTS, "--env"
    )
    # Pass a concrete environment: the subsidiary list lives in settings.yaml's shared
    # `defaults`, so any resolved env answers the same, but letting it resolve its own
    # would route through $ENV — which this layer allows to hold a list ("dev,stg"), and
    # which env_config rightly rejects as a single environment name.
    subsidiaries, subs_expanded = _resolve_dimension(
        _requested(pytest_config, "--subsidiary", "SUBSIDIARY"),
        configured_subsidiaries(envs[0]),
        "--subsidiary",
        upper=True,
    )
    data_sets, sets_expanded = _resolve_dimension(
        _requested(pytest_config, "--data-set", "DATA_SET"), DATA_SETS, "--data-set"
    )
    expanded = envs_expanded or subs_expanded or sets_expanded
    return [
        RunTarget(env=env, subsidiary=subsidiary, data_set=data_set, expanded=expanded)
        for env, subsidiary, data_set in itertools.product(envs, subsidiaries, data_sets)
    ]


def _has_test_data(target: RunTarget, module_path: str) -> bool:
    """Report whether ``module_path`` has a test-data directory for ``target``.

    Resolves through ``Config.test_data_dir`` rather than building the path here, so the
    ``test_data/<module>/<env>/<subsidiary>/<data_set>/`` layout keeps exactly one
    definition (docs/context/test-data-conventions.md).

    Args:
        target: The combination to check.
        module_path: The module's location, e.g. ``"purchase_checker/login"``.

    Returns:
        True when the directory exists. False also covers a combination whose
        configuration cannot be resolved at all (a missing ``.env.<env>``, say) — only
        ever consulted for expanded targets, so an explicitly requested combination still
        runs and reports that error properly instead of vanishing.
    """
    try:
        get_config(
            env=target.env, subsidiary=target.subsidiary, data_set=target.data_set
        ).test_data_dir(module_path)
    except ConfigError:
        return False
    return True


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Parametrize every ``config``-consuming test across the run matrix.

    Applied here rather than per module so no orchestrator has to know the matrix exists:
    a test keeps taking a single ``config`` and simply runs once per combination.

    A test module that declares ``MODULE_PATH`` (the convention every module orchestrator
    follows) additionally has its *expanded* combinations filtered: those without authored
    test data are marked skipped, with the reason naming the missing directory. They are
    emitted as skips rather than dropped silently so ``-ra`` still shows what a bare
    ``pytest`` did not cover. Suite-level orchestrators (e2e, critical path) declare no
    ``MODULE_PATH`` and are left untouched.

    Args:
        metafunc: The function being collected.

    Returns:
        None.

    Raises:
        pytest.UsageError: If an option names an unconfigured env/subsidiary/data set.
    """
    if "run_target" not in metafunc.fixturenames:
        return

    module_path = getattr(metafunc.module, "MODULE_PATH", None)
    params = []
    for target in resolve_run_targets(metafunc.config):
        marks = ()
        if target.expanded and module_path and not _has_test_data(target, module_path):
            marks = pytest.mark.skip(
                reason=(
                    f"no test data authored for {module_path} at "
                    f"{target.env}/{target.subsidiary}/{target.data_set}"
                )
            )
        params.append(pytest.param(target, id=target.id, marks=marks))
    metafunc.parametrize("run_target", params, indirect=True, scope="session")


@pytest.fixture(scope="session")
def run_target(request: pytest.FixtureRequest) -> RunTarget:
    """The combination the current test instance targets.

    Populated by :func:`pytest_generate_tests`. Session-scoped with one instance per
    combination, so every fixture derived from it is built once per combination rather
    than once per test.

    Args:
        request: Pytest request carrying the parametrized value.

    Returns:
        The :class:`RunTarget` for this test instance.
    """
    return request.param


@pytest.fixture(scope="session")
def run_targets(request: pytest.FixtureRequest) -> list[RunTarget]:
    """Every combination this run covers, unparametrized.

    For run-wide concerns that must see the whole matrix rather than one cell of it —
    naming the log file, reporting the run's scope once at startup.

    Args:
        request: Pytest request, used to read the CLI options.

    Returns:
        The resolved matrix, in execution order.
    """
    return resolve_run_targets(request.config)


@pytest.fixture(scope="session")
def config(run_target: RunTarget) -> Config:
    """Resolved configuration (``lib.core.config.env_config.Config``) for one combination.

    Session-scoped **per combination**: a matrix run holds one immutable instance per
    cell, and every fixture and module within a cell reads the same one, so a single test
    instance can't half-target two environments.

    Args:
        run_target: The combination this test instance covers.

    Returns:
        The resolved :class:`Config`.

    Raises:
        ConfigError: If the env/subsidiary is unknown, the secrets file is missing
            outside CI, or a configured cert path doesn't exist.
    """
    resolved = get_config(
        env=run_target.env, subsidiary=run_target.subsidiary, data_set=run_target.data_set
    )
    logging.getLogger(__name__).info(
        "Run target: env=%s subsidiary=%s data_set=%s",
        resolved.env,
        resolved.subsidiary,
        resolved.data_set,
    )
    return resolved


def _dimension_values(targets: Sequence[RunTarget], attribute: str) -> list[str]:
    """Return the distinct values one dimension takes across the matrix, in order.

    Args:
        targets: The resolved run matrix.
        attribute: ``"env"``, ``"subsidiary"`` or ``"data_set"``.

    Returns:
        The distinct values, first-seen order preserved so the run's own ordering shows.
    """
    return list(dict.fromkeys(getattr(target, attribute) for target in targets))


@pytest.fixture(scope="session", autouse=True)
def _logging(run_targets: list[RunTarget]) -> None:
    """Initialize logging once per session and stamp Allure run metadata.

    Autouse so no module has to remember to request it — an unconfigured logger would
    silently drop the DEBUG payload/query records that make a failure diagnosable.

    Depends on the whole matrix rather than one ``config``: ``setup_logging`` configures
    the root logger exactly once, so a matrix run keyed off a single cell would name its
    file after whichever combination happened to be built first and then quietly collect
    every other combination's records under that name. The name instead lists each
    dimension's values (``run_dev_MJP+KOR+USA_test.log``), which stays true to CLAUDE.md's
    ``logs/<suite>_<env>_<subsidiary_cd>_...`` convention for the single-combination case
    and remains honest for a matrix.

    The metadata call is retained but self-disabling: ``write_run_metadata`` no-ops while
    ``features.allure_enabled`` is false (the current default), so a run writes its log
    file as always and nothing under ``reports/allure-results``.

    Args:
        run_targets: Every combination this run covers.

    Returns:
        None.
    """
    envs, subsidiaries, data_sets = (
        "+".join(_dimension_values(run_targets, attribute))
        for attribute in ("env", "subsidiary", "data_set")
    )
    setup_logging(level=logging.INFO, log_file=f"run_{envs}_{subsidiaries}_{data_sets}.log")
    write_run_metadata(envs, subsidiaries, data_sets)
    logging.getLogger(__name__).info(
        "Run matrix: %d combination(s) — env=%s subsidiary=%s data_set=%s",
        len(run_targets),
        envs,
        subsidiaries,
        data_sets,
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
        # The report covers the whole session, so the flags are read from the matrix's
        # first combination rather than a per-test config — they live in settings.yaml's
        # `defaults`, so every combination answers identically.
        first = resolve_run_targets(session.config)[0]
        config = get_config(env=first.env, subsidiary=first.subsidiary, data_set=first.data_set)
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
