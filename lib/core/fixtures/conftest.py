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
import re
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
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

# Wall-clock start of the run, stamped in pytest_configure and read by
# pytest_terminal_summary. Module-level because the two are hooks, not fixtures, so there is
# no request to carry state on; None means logging was never set up (a --collect-only run).
_SESSION_STARTED: float | None = None


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
    """Validate the run-target options and open this run's log file, before collection.

    Two jobs, both of which have to happen before anything else runs.

    **Validate.** Resolving the matrix here as well as during collection is deliberate, not
    redundant: a :class:`pytest.UsageError` raised from ``pytest_generate_tests`` surfaces
    as a collection error wrapped in a traceback, while the same error raised here prints as
    a single ``ERROR:`` line. A typo in ``--env`` is the likeliest mistake at this CLI, and
    it should read like a usage message rather than a crash.

    **Start logging.** This is the earliest hook with the options parsed, so configuring the
    file handler here — rather than from a fixture at first test setup — is what makes the
    file cover the *whole* run: anything logged during collection or fixture setup used to
    be written before any handler existed and was silently dropped. Skipped for
    ``--collect-only``, which runs no tests and would otherwise leave a near-empty file
    behind every time someone inspects the matrix.

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
    targets = resolve_run_targets(config)
    if config.getoption("--collect-only"):
        return

    global _SESSION_STARTED
    _SESSION_STARTED = time.monotonic()

    envs, subsidiaries, data_sets = _dimension_summary(targets)
    log_file = _log_file_name(config, targets)
    setup_logging(level=logging.INFO, log_file=log_file)
    write_run_metadata(envs, subsidiaries, data_sets)
    logging.getLogger(__name__).info(
        "Run matrix: %d combination(s) — env=%s subsidiary=%s data_set=%s — logging to %s",
        len(targets),
        envs,
        subsidiaries,
        data_sets,
        log_file,
    )


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


# Longest suite label allowed in a log file name. The full name also carries the matrix and
# a timestamp, and these files live under an already-deep OneDrive path, so the one
# unbounded part is capped rather than risking Windows' path limit.
_LABEL_MAX_CHARS = 40

# Anything outside this set is replaced in a log file's suite label. Notably excludes ":"
# and the path separators, which would turn the file name into a path and take the log out
# of logs/ (see _suite_label).
_UNSAFE_LABEL_CHARS = re.compile(r"[^A-Za-z0-9_+.-]+")


def _suite_label(pytest_config: pytest.Config) -> str:
    """Summarise *what* a run targeted, for the log file name.

    Derived from the paths pytest was pointed at, because that is what a reader actually
    wants to distinguish two log files by — `login` versus `etl-gdb` versus the whole
    suite. Reduces each argument to its position under ``lib/app/``:

    * ``lib/app/modules/purchase_checker/login`` -> ``purchase_checker-login``
    * ``lib/app/modules/etl/gdb/orchestrator.py`` -> ``etl-gdb``
    * ``lib/app/e2e`` -> ``e2e``
    * ``lib/app`` (the ``testpaths`` default, i.e. no path given) -> ``all``
    * anything outside the tree -> just its tail, e.g. ``some_check``

    The result is sanitised to ``[A-Za-z0-9_+.-]``, which is a correctness requirement
    rather than tidiness: an absolute Windows path reduces to a label containing the drive
    colon, and ``Path("logs") / "C:-Users-..."`` silently discards the ``logs`` component
    because pathlib reads ``C:`` as a drive — writing the run's log somewhere other than
    where it was asked to.

    Args:
        pytest_config: The pytest config; ``args`` holds the paths given on the command
            line, or ``testpaths`` from pytest.ini when none were.

    Returns:
        A filename-safe label, several targets joined by ``+``, truncated to
        :data:`_LABEL_MAX_CHARS`. Never empty — falls back to ``"all"`` so a log file is
        always named consistently.
    """
    labels: list[str] = []
    for argument in pytest_config.args:
        # Drop any ``::test_name`` selector, and normalise Windows separators.
        path = argument.replace("\\", "/").split("::")[0].strip("/")
        # The testpaths default, relative or absolute: the whole suite.
        if path.endswith("lib/app"):
            label = "all"
        else:
            for root in ("lib/app/modules/", "lib/app/"):
                if root in path:
                    path = path.split(root, 1)[1]
                    break
            else:
                # Outside lib/app — an ad-hoc file, or an absolute path from elsewhere.
                # Only its tail carries meaning, and dropping the rest is also what keeps a
                # drive letter out of the name.
                path = path.rsplit("/", 1)[-1]
            # A module is identified by its directory; the file inside it adds nothing.
            label = path.removesuffix(".py").replace("/", "-").removesuffix("-orchestrator")
        label = _UNSAFE_LABEL_CHARS.sub("-", label).strip("-") or "all"
        if label not in labels:
            labels.append(label)
    return ("+".join(labels) or "all")[:_LABEL_MAX_CHARS]


def _log_file_name(pytest_config: pytest.Config, targets: Sequence[RunTarget]) -> str:
    """Build this run's log file name: what ran, against what, and when.

    Timestamped to the second so **no run ever overwrites or appends to another's log**.
    That matters more than it looks: the handler opens in append mode, so before the
    timestamp a second run against the same matrix silently continued the previous file,
    and two runs' records interleaved under one name with no boundary between them. A
    distinct file per run is what makes "the log from the 14:39 failure" a thing you can
    actually retrieve.

    Shape follows CLAUDE.md's ``<suite>_<env>_<subsidiary_cd>_<timestamp>`` convention,
    extended with the data set and with each dimension listing every value the matrix
    covered.

    Args:
        pytest_config: The pytest config, for the suite label.
        targets: The resolved run matrix, for the env/subsidiary/data-set parts.

    Returns:
        A file name such as
        ``purchase_checker-login_dev_MJP+KOR_real+test_20260812-143912.log``.
    """
    envs, subsidiaries, data_sets = _dimension_summary(targets)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{_suite_label(pytest_config)}_{envs}_{subsidiaries}_{data_sets}_{stamp}.log"


def _dimension_summary(targets: Sequence[RunTarget]) -> tuple[str, str, str]:
    """Summarise the matrix as three ``+``-joined strings.

    Args:
        targets: The resolved run matrix.

    Returns:
        ``(envs, subsidiaries, data_sets)``, each listing that dimension's distinct values
        in run order — e.g. ``("dev", "MJP+KOR", "real+test")``. Shared by the log file's
        name and the run-scope line logged at startup so the two can't disagree.
    """
    envs, subsidiaries, data_sets = (
        "+".join(_dimension_values(targets, attribute))
        for attribute in ("env", "subsidiary", "data_set")
    )
    return envs, subsidiaries, data_sets


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """Record every test's outcome in the run log, not just its flow.

    Why this hook exists: the orchestrators log what they *do*, and pytest tracks what
    *happened*, and those went to two different places — the log file ended at the last
    "FE: finished" line while the pass/fail verdict, the failure detail and the skip reason
    existed only in terminal output that scrolls away. Reading a saved log then meant
    inferring the result from the absence of errors. Mirroring pytest's own verdicts into
    the same file makes it the single record of a run.

    ``report.longreprtext`` is included for failures, which is what carries an
    orchestrator's assembled summary (``5/6 login test case(s) failed: …``) — that text is
    produced by ``pytest.fail`` and never passes through ``logging`` otherwise.

    Levels follow CLAUDE.md: a failed test case is ERROR; a skip is INFO, because the run
    matrix skips unauthored combinations by design and WARNING would mean 120 warnings on a
    bare run.

    Args:
        report: The phase report pytest just completed. Setup/teardown phases are reported
            only when they failed — a passing setup is noise — so a normal test contributes
            exactly one line.

    Returns:
        None.
    """
    logger = logging.getLogger(__name__)
    if report.failed:
        # An exception outside the test body is an ERROR in pytest's own vocabulary; keeping
        # the distinction tells "the harness broke" apart from "the assertion failed".
        outcome = "FAILED" if report.when == "call" else f"ERROR ({report.when})"
        logger.error(
            "Test %s: %s (%.2fs)%s",
            report.nodeid,
            outcome,
            report.duration,
            f"\n{report.longreprtext}" if report.longreprtext else "",
        )
    elif report.skipped:
        logger.info("Test %s: SKIPPED — %s", report.nodeid, _skip_reason(report))
    elif report.when == "call":
        logger.info("Test %s: PASSED (%.2fs)", report.nodeid, report.duration)


def _skip_reason(report: pytest.TestReport) -> str:
    """Extract a skip's reason text from its report.

    Args:
        report: A skipped phase report. pytest models the reason as a
            ``(file, line, "Skipped: <reason>")`` triple, which is not worth making every
            caller unpack.

    Returns:
        The reason, or ``"<no reason given>"`` when the report carries none — never raises,
        since a logging path must not fail a run.
    """
    longrepr = getattr(report, "longrepr", None)
    if isinstance(longrepr, tuple) and len(longrepr) == 3:
        return str(longrepr[2]).removeprefix("Skipped: ")
    return str(longrepr) if longrepr else "<no reason given>"


def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter, exitstatus: int, config: pytest.Config
) -> None:
    """Write the session's closing tally into the run log.

    The counterpart to :func:`pytest_runtest_logreport`: that records each test, this
    records the run. Without it the log file has every verdict but no bottom line, so
    answering "did this run pass?" means tallying by hand. Logged at ERROR when anything
    failed so the file's severity reflects the run's outcome, which is what makes
    ``grep ERROR`` on a log directory a useful triage step.

    Args:
        terminalreporter: pytest's reporter, whose ``stats`` hold the per-outcome reports.
        exitstatus: The session's exit status, recorded verbatim — ``0`` is a pass, ``1``
            tests failed, ``2`` interrupted, ``4`` usage error.
        config: The pytest config. Unused; accepted because pluggy matches hooks by
            parameter name and omitting it would not change what is called.

    Returns:
        None.
    """
    stats = terminalreporter.stats
    tally = ", ".join(
        f"{len(stats[outcome])} {outcome}"
        for outcome in ("passed", "failed", "error", "skipped", "xfailed", "xpassed")
        if stats.get(outcome)
    )
    elapsed = time.monotonic() - _SESSION_STARTED if _SESSION_STARTED else 0.0
    failures = [report.nodeid for report in stats.get("failed", [])]
    failures += [report.nodeid for report in stats.get("error", [])]

    logger = logging.getLogger(__name__)
    logger.log(
        logging.ERROR if failures else logging.INFO,
        "Session summary: %s in %.2fs (exit status %s)%s",
        tally or "no tests ran",
        elapsed,
        exitstatus,
        "\n  " + "\n  ".join(failures) if failures else "",
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
