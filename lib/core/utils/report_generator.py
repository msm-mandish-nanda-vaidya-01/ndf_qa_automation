"""Allure attachment + report generation helpers.

PLACEHOLDER — signatures only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def attach_json(name: str, payload: Any) -> None:
    """Attach a pretty-printed JSON payload (BE response, DB row) to the Allure report."""
    raise NotImplementedError("TODO: implement allure JSON attachment")


def attach_text(name: str, body: str) -> None:
    """Attach plain text (SQL, query DSL, log excerpt)."""
    raise NotImplementedError("TODO: implement allure text attachment")


def attach_screenshot(name: str, image_bytes: bytes) -> None:
    """Attach a PNG screenshot, used on FE failure."""
    raise NotImplementedError("TODO: implement allure image attachment")


def attach_table(name: str, rows: list[dict[str, Any]]) -> None:
    """Attach query results as a CSV/HTML table."""
    raise NotImplementedError("TODO: implement allure table attachment")


def write_run_metadata(env: str, subsidiary: str, data_set: str) -> None:
    """Write ``environment.properties`` / ``executor.json`` into ``reports/allure-results``."""
    raise NotImplementedError("TODO: implement allure environment metadata")


def generate_report(results_dir: Path | str, output_dir: Path | str, *, clean: bool = True) -> None:
    """Shell out to ``allure generate``. See also ``make report``."""
    raise NotImplementedError("TODO: implement allure generate wrapper")


def summarize(results_dir: Path | str) -> dict[str, Any]:
    """Return a pass/fail/skip summary — for CI comments and Slack/Teams notifications."""
    raise NotImplementedError("TODO: implement run summary")
