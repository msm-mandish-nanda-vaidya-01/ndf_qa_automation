"""Allure attachment + report generation helpers.

Exists so modules never call ``allure`` directly. Per CLAUDE.md, a failure should carry
the whole picture in one place — the BE request/response, the FE screenshot and URL, and
the query/result of whichever DB check ran — not just the layer that happened to raise.
Centralising the attachment calls is what keeps that consistent across modules and lets
the "attach everything, not only the failing layer" rule be enforced in one file.

Attachment helpers are safe to call when Allure isn't active (a plain ``pytest`` run
with no ``--alluredir``, or an orchestrator invoked outside pytest): they degrade to a
debug log rather than raising, so reporting concerns can never fail a test. That applies
to serialisation too — an unserialisable payload is attached as a note, not raised.

:func:`generate_report` is the deliberate exception: rendering the HTML site is an explicit
request that depends on an external tool, so it raises :class:`AllureCliError` when that
tool is missing. The automatic post-run call in ``lib/core/fixtures/conftest.py`` catches
that and warns, so a machine without the Allure commandline still gets a green run.

**Redaction is the caller's job.** These helpers serialise what they are given and know
nothing about any module's secrets — see ``attach_module_results``.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

from lib.core.config.env_config import REPORTS_ROOT

logger = logging.getLogger(__name__)

ALLURE_RESULTS_DIR = REPORTS_ROOT / "allure-results"
ALLURE_REPORT_DIR = REPORTS_ROOT / "allure-report"


class AllureCliError(RuntimeError):
    """Raised when the external Allure commandline is unavailable or failed.

    Distinct from the attachment helpers' silent degradation: generating the site is an
    explicit request, so it reports honestly. The automatic post-run generation in
    ``conftest`` catches this and warns rather than failing the test session.
    """


def _attach(name: str, body: str | bytes, attachment_type_name: str) -> None:
    """Attach a body to the current Allure step, or log it away if Allure is inactive.

    Why the fallback: orchestrators run both under pytest (Allure active) and directly
    from the CLI (not active). A reporting call must never be the reason a run fails, so
    an unavailable Allure is a debug-level non-event. The attachment type is named
    rather than passed as an object so callers never have to import ``allure``
    themselves — which would reintroduce the hard dependency this guards against.

    Args:
        name: Attachment title shown in the report.
        body: Attachment content.
        attachment_type_name: Member name on ``allure.attachment_type``, e.g. ``"JSON"``.

    Returns:
        None.
    """
    try:
        import allure
    except ImportError:  # pragma: no cover - allure-pytest is a hard requirement in CI
        logger.debug("allure not installed; skipping attachment %r", name)
        return

    try:
        allure.attach(
            body,
            name=name,
            attachment_type=getattr(allure.attachment_type, attachment_type_name),
        )
    except Exception as exc:  # noqa: BLE001 - reporting must never fail a test
        logger.debug("Could not attach %r to the Allure report: %s", name, exc)


def attach_json(name: str, payload: Any) -> None:
    """Attach a pretty-printed JSON payload (BE response, DB row) to the Allure report.

    Args:
        name: Attachment title, e.g. ``"BE response"``.
        payload: Any JSON-serialisable object. Values that aren't serialisable are
            stringified rather than raising — a report is worth more than strictness
            here.

    Returns:
        None.
    """
    try:
        body = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
    except (TypeError, ValueError) as exc:
        # Serialising happens here, outside _attach's guard, so it must be guarded too —
        # otherwise a circular reference or a non-str dict key fails the whole run at the
        # reporting line, after every test has already passed.
        logger.debug("Could not serialise attachment %r as JSON: %s", name, exc)
        _attach(name, f"<unserialisable payload: {type(exc).__name__}: {exc}>", "TEXT")
        return
    _attach(name, body, "JSON")


def attach_text(name: str, body: str) -> None:
    """Attach plain text (SQL, query DSL, log excerpt).

    Args:
        name: Attachment title.
        body: Text content.

    Returns:
        None.
    """
    _attach(name, body, "TEXT")


def attach_screenshot(name: str, image_bytes: bytes) -> None:
    """Attach a PNG screenshot, used on FE failure.

    Args:
        name: Attachment title, e.g. ``"FE: login page"``.
        image_bytes: Raw PNG bytes, e.g. from ``page.screenshot()``.

    Returns:
        None.
    """
    _attach(name, image_bytes, "PNG")


def attach_module_results(module: str, results: list[dict[str, Any]]) -> None:
    """Attach an orchestrator's per-test-case results as one report artifact.

    Why: an orchestrator collects every layer's outcome per test case and does not
    short-circuit on failure, so by the end of a run it holds the full context CLAUDE.md
    asks for. This turns that into a single attachment — a per-case summary plus the raw
    results — so a reader sees which cases failed and at which layer without expanding
    every step.

    **Results must already be redacted.** This serialises whatever it is given, so a
    module that carries a token or password on a result object has to project it to a safe
    dict first (see ``LoginResult.to_report_dict``). This helper deliberately knows nothing
    about any module's secrets and cannot redact on their behalf.

    Args:
        module: Module path for the title, e.g. ``"purchase_checker/login"``.
        results: One result dict per test case, as returned by the module
            orchestrator's ``run``. Each is expected to carry ``test_case``, ``errors``
            and optionally ``skipped`` keys; other keys are passed through untouched.
            Malformed entries are tolerated rather than raising — a reporting helper must
            not be the thing that fails a run.

    Returns:
        None.
    """
    summary = [
        {
            "test_case": result.get("test_case", "<unnamed>"),
            "failed_stages": [
                error.get("stage", "<unknown>")
                for error in (result.get("errors") or [])
                if isinstance(error, dict)
            ],
            "skipped_stages": [
                skip.get("stage", "<unknown>")
                for skip in (result.get("skipped") or [])
                if isinstance(skip, dict)
            ],
            "passed": not (result.get("errors") or []),
        }
        for result in results
    ]
    failed = sum(1 for row in summary if not row["passed"])
    logger.info("%s: %d/%d test case(s) passed", module, len(summary) - failed, len(summary))
    attach_json(f"{module}: summary", summary)
    attach_json(f"{module}: full results", results)


def write_run_metadata(env: str, subsidiary: str, data_set: str) -> None:
    """Write ``environment.properties`` into ``reports/allure-results``.

    Why: an Allure report is read after the fact, often by someone who didn't launch the
    run. Without this, nothing in the report says which environment or subsidiary it
    describes, and a dev failure looks identical to a prod one.

    Creates the results directory if it doesn't exist yet, so this can run before pytest
    has written anything.

    Args:
        env: The run's resolved environment.
        subsidiary: The run's resolved subsidiary code.
        data_set: ``"real"`` or ``"test"``.

    Returns:
        None.
    """
    ALLURE_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    properties = "\n".join([f"env={env}", f"subsidiary={subsidiary}", f"data_set={data_set}"])
    (ALLURE_RESULTS_DIR / "environment.properties").write_text(properties + "\n", encoding="utf-8")
    logger.debug("Wrote Allure run metadata for %s/%s/%s", env, subsidiary, data_set)


def generate_report(
    results_dir: Path | str = ALLURE_RESULTS_DIR,
    output_dir: Path | str = ALLURE_REPORT_DIR,
    *,
    clean: bool = True,
) -> None:
    """Render the raw Allure results into a browsable HTML site.

    Why this is a subprocess and not a library call: ``allure-pytest`` only writes result
    JSON. Turning those into a report requires the Allure **commandline**, a separate
    Java-based tool that is not a Python dependency and will not be present on every
    machine.

    Called automatically at the end of a pytest session by ``conftest``'s
    ``pytest_sessionfinish`` hook. This function raises when the CLI is missing or fails;
    that caller catches and warns, so a missing CLI never turns a passing run red.

    Deliberately version-agnostic across Allure 2 (Java) and Allure 3 (Node). The two
    CLIs share ``generate <results> -o <output>`` but diverge on everything else — notably
    Allure 3 removed ``--clean`` and exits 1 when given it. So the stale output directory
    is removed here in Python rather than delegated to a flag, and no flag beyond ``-o``
    is passed.

    Args:
        results_dir: Directory holding the raw ``*-result.json`` files.
        output_dir: Directory to write the generated site into.
        clean: Remove ``output_dir`` first, so a stale site from a previous run is
            replaced rather than merged into.

    Returns:
        None.

    Raises:
        AllureCliError: If the ``allure`` executable isn't on ``PATH``, if it exits
            non-zero, or if ``results_dir`` holds no results to render.
    """
    results_path = Path(results_dir)
    output_path = Path(output_dir)

    if not results_path.is_dir() or not any(results_path.glob("*result.json")):
        raise AllureCliError(
            f"No Allure results to render in {results_path}. "
            "Run the suite first, or check --alluredir in pytest.ini."
        )

    executable = shutil.which("allure")
    if executable is None:
        raise AllureCliError(
            "The 'allure' commandline is not on PATH, so the HTML report cannot be "
            "generated. Install it (scoop install allure / npm i -g allure-commandline / "
            f"brew install allure), then run: allure generate {results_path} "
            f"-o {output_path} --clean"
        )

    if clean and output_path.exists():
        shutil.rmtree(output_path, ignore_errors=True)

    command = [executable, "generate", str(results_path), "-o", str(output_path)]
    logger.debug("Generating Allure report: %s", " ".join(command))
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise AllureCliError(
            f"'allure generate' exited {completed.returncode}: "
            f"{(completed.stderr or completed.stdout).strip()[:500]}"
        )
    logger.info("Allure report generated at %s", _report_entry_point(output_path))


def _report_entry_point(output_path: Path) -> Path:
    """Return the ``index.html`` a human should actually open.

    Why this isn't just ``output_path / "index.html"``: the two Allure generations lay the
    output out differently. Allure 2 writes ``index.html`` at the root; Allure 3 renders
    through plugins and nests it one level down (``<output>/awesome/index.html``). Logging
    the resolved path means the run tells you where the report is instead of you guessing
    per CLI version.

    Args:
        output_path: The directory ``allure generate`` was pointed at.

    Returns:
        Path of the shallowest ``index.html`` found, or ``output_path`` itself if the
        layout is unrecognised — the log line stays useful either way.
    """
    candidates = sorted(output_path.glob("**/index.html"), key=lambda p: len(p.parts))
    return candidates[0] if candidates else output_path
