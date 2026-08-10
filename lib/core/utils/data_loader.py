"""Test-data loading from ``test_data/<module>/<env>/<subsidiary>/<data_set>/``.

Resolve the directory with ``get_config().test_data_dir("etl/gdb")``, then load
files from it through these helpers.

PLACEHOLDER — signatures only. Fill in once the test-data file formats are fixed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def load_json(path: Path | str) -> Any:
    """Load a JSON file."""
    raise NotImplementedError("TODO: implement JSON loader")


def load_yaml(path: Path | str) -> Any:
    """Load a YAML file."""
    raise NotImplementedError("TODO: implement YAML loader")


def load_csv(path: Path | str) -> list[dict[str, Any]]:
    """Load a CSV file as a list of row dicts."""
    raise NotImplementedError("TODO: implement CSV loader")


def load_excel(path: Path | str, sheet: str | int = 0) -> list[dict[str, Any]]:
    """Load one sheet of an .xlsx file as a list of row dicts."""
    raise NotImplementedError("TODO: implement Excel loader")


def load_case(module_path: str, name: str) -> dict[str, Any]:
    """Load a named case file for a module, resolving env/subsidiary/data_set automatically.

    Example: ``load_case("etl/gdb", "happy_path")``.
    """
    raise NotImplementedError("TODO: resolve via get_config().test_data_dir() and dispatch by suffix")


def load_all_cases(module_path: str) -> list[dict[str, Any]]:
    """Load every case file in a module's test-data directory. Useful for parametrization."""
    raise NotImplementedError("TODO: implement bulk case loader")
