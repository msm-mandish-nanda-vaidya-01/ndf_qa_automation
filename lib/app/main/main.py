"""CLI entrypoint. Wraps pytest so runs are reproducible and self-documenting.

    python -m lib.app.main.main --suite critical-path --env stg
    python -m lib.app.main.main --suite module --module etl/gdb --data-set real
    python -m lib.app.main.main --suite e2e --env dev --report

Argparse-based on purpose: every run is expressible as a single copy-pasteable
command, which is what CI and bug reports need.

The three run-target options must forward through to pytest **verbatim**, including when
they are repeated or comma-separated: `lib/core/fixtures/conftest.py` owns their meaning
(multi-value, and "omitted means every configured value"), and re-deriving a single
default here would silently contradict it.

PLACEHOLDER — implementation to be filled in.
"""

from __future__ import annotations

import argparse
import sys

SUITES = {
    "module": "lib/app/modules",
    "e2e": "lib/app/e2e",
    "critical-path": "lib/app/critical_path",
    "all": "lib/app",
}


def build_parser() -> argparse.ArgumentParser:
    """Define the CLI surface.

    Options to implement:
      --suite {module,e2e,critical-path,all}   which suite to run (required)
      --module PATH                            e.g. etl/gdb; required for --suite module
      --env ENV                                target environment(s). Repeatable and
                                               comma-separated (--env dev,stg)
                                               [default: $ENV, else every environment]
      --subsidiary CODE                        subsidiary code(s), e.g. MJP. Same
                                               repeatable/comma-separated form
                                               [default: $SUBSIDIARY, else all]
      --data-set KIND                          test-data variant(s), real | test. Same
                                               form  [default: $DATA_SET, else both]
      -m, --markers EXPR                       extra pytest marker expression
      -k EXPR                                  pytest name filter
      -n, --parallel N                         xdist workers ("auto" allowed)
      --headed                                 override features.fe_headless
      --reruns N                               retry flaky tests
      --report                                 run `allure generate` afterwards; while
                                               features.allure_enabled is false no run
                                               produces results, so there is nothing to
                                               render
      --dry-run                                print the pytest command and exit
      -v, --verbose                            raise log level to DEBUG
    """
    raise NotImplementedError("TODO: define arguments")


def resolve_target(args: argparse.Namespace) -> str:
    """Map ``--suite``/``--module`` to a pytest path under ``SUITES``.

    Errors out when ``--suite module`` is given without ``--module``, and when the
    resolved module directory does not exist.
    """
    raise NotImplementedError("TODO: resolve and validate the pytest target path")


def build_pytest_args(args: argparse.Namespace) -> list[str]:
    """Translate parsed CLI args into a pytest argv list.

    Passes env/subsidiary/data-set through as pytest CLI options (see
    ``lib/core/fixtures/conftest.py``) rather than mutating os.environ.
    """
    raise NotImplementedError("TODO: build the pytest argv")


def main(argv: list[str] | None = None) -> int:
    """Parse args, run pytest, optionally generate the report. Returns the exit code."""
    raise NotImplementedError("TODO: parse -> build -> pytest.main -> optional report")


if __name__ == "__main__":
    sys.exit(main())
