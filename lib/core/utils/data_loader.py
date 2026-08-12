"""Test-data loading from ``test_data/<module>/<env>/<subsidiary>/<data_set>/``.

Every module loads its cases through here so no module builds a ``test_data/...`` path
by hand — the directory layout is a convention (docs/context/test-data-conventions.md),
and hand-built paths are how it silently drifts.

There is no shared schema across modules: each module's ``be.py``/``fe.py`` defines what
its own files contain. This loader therefore parses files into a :class:`TestCase` that
exposes whatever fields the file happens to have, and deliberately knows nothing about
how to interpret an ``expected`` block — that resolution belongs in the owning module.

Two entry points, for the two ways cases get used:

* :func:`load` — every case in a module's folder, one :class:`TestCase` per file. This
  is what an orchestrator's data-driven fan-out iterates.
* :func:`load_case` / :func:`load_all_cases` — raw dicts, for pytest parametrization
  and for callers that want the unwrapped file content.
"""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from lib.core.config.env_config import ConfigError, get_config

logger = logging.getLogger(__name__)

# File suffixes recognised as test-data cases, mapped to their loader below. Anything
# else in a test-data folder (README, .gitkeep) is ignored rather than erroring, so
# documenting a folder doesn't break the run.
_CASE_SUFFIXES = (".json", ".yaml", ".yml", ".csv", ".xlsx")


@dataclass(frozen=True)
class TestCase:
    """One parsed test-data file.

    Why a wrapper rather than the raw dict: modules address fields as attributes
    (``test_case.name``, ``test_case.payload``), and the scenario name has to be
    reliable because it's what every log line and report row is keyed by. Everything
    else falls through to the file's own fields, so a module can add whatever shape it
    needs without touching this loader.

    Attributes:
        name: Scenario name. Taken from the file's ``name`` or ``case_name`` field,
            falling back to the file stem — so a file that forgot the field is still
            identifiable in a report.
        description: The file's ``description`` field, or empty string.
        path: Absolute path the case was read from, for failure messages.
        data: The file's full parsed content.
    """

    name: str
    description: str
    path: Path
    data: dict[str, Any] = field(default_factory=dict)

    def __getattr__(self, item: str) -> Any:
        """Expose the file's own fields as attributes.

        Only called for names not already defined on the dataclass, so declared fields
        always win over a same-named key in the file.

        The two guards below are not defensive padding — without them this method
        infinitely recurses. ``copy.deepcopy`` and ``pickle`` rebuild an instance via
        ``cls.__new__(cls)``, which has no ``data`` attribute yet, and then probe it for
        ``__deepcopy__``/``__setstate__``/``__reduce_ex__``. Each probe misses, lands
        here, touches ``self.data``, misses again, and recurses until the stack blows.
        That matters in practice: ``pytest-xdist`` pickles objects across worker
        boundaries.

        Args:
            item: Field name being accessed.

        Returns:
            The value of that key in :attr:`data`.

        Raises:
            AttributeError: If the file has no such field, if ``item`` is a dunder, or if
                the instance is still being reconstructed. The message names the file so
                the fix is obvious without opening the loader.
        """
        if item.startswith("__") or "data" not in self.__dict__:
            raise AttributeError(item)
        try:
            return self.__dict__["data"][item]
        except KeyError:
            raise AttributeError(
                f"Test case '{self.name}' ({self.path}) has no field '{item}'"
            ) from None

    def get(self, item: str, default: Any = None) -> Any:
        """Read an optional field without raising when it's absent.

        Args:
            item: Field name.
            default: Returned when the field is missing or explicitly null.

        Returns:
            The field's value, or ``default``.
        """
        value = self.data.get(item, default)
        return default if value is None else value


def load_json(path: Path | str) -> Any:
    """Load a JSON file.

    Args:
        path: File to read.

    Returns:
        The parsed content.

    Raises:
        json.JSONDecodeError: If the file is not valid JSON.
    """
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_yaml(path: Path | str) -> Any:
    """Load a YAML file.

    Args:
        path: File to read.

    Returns:
        The parsed content; ``None`` for an empty file.

    Raises:
        yaml.YAMLError: If the file is not valid YAML.
    """
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def load_csv(path: Path | str) -> list[dict[str, Any]]:
    """Load a CSV file as a list of row dicts, keyed by the header row.

    Args:
        path: File to read.

    Returns:
        One dict per data row. Empty list for a header-only file.
    """
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_excel(path: Path | str, sheet: str | int = 0) -> list[dict[str, Any]]:
    """Load one sheet of an .xlsx file as a list of row dicts, keyed by the header row.

    Args:
        path: File to read.
        sheet: Sheet name, or zero-based index into the workbook's sheet order.

    Returns:
        One dict per data row below the header. Fully blank rows are skipped, since
        trailing empty rows are a common artifact of hand-edited spreadsheets.

    Raises:
        ConfigError: If ``sheet`` names a sheet the workbook doesn't contain.
    """
    from openpyxl import load_workbook

    workbook = load_workbook(Path(path), read_only=True, data_only=True)
    try:
        if isinstance(sheet, int):
            worksheet = workbook[workbook.sheetnames[sheet]]
        elif sheet in workbook.sheetnames:
            worksheet = workbook[sheet]
        else:
            raise ConfigError(
                f"Sheet '{sheet}' not found in {path}. "
                f"Available: {', '.join(workbook.sheetnames)}"
            )

        rows = worksheet.iter_rows(values_only=True)
        header = next(rows, None)
        if header is None:
            return []
        columns = [str(cell) if cell is not None else "" for cell in header]
        return [
            dict(zip(columns, row, strict=False))
            for row in rows
            if any(cell is not None for cell in row)
        ]
    finally:
        workbook.close()


def _load_file(path: Path) -> Any:
    """Dispatch to the right loader for a file, based on its suffix.

    Args:
        path: File to read.

    Returns:
        The parsed content.

    Raises:
        ConfigError: If the suffix isn't one of :data:`_CASE_SUFFIXES`.
    """
    suffix = path.suffix.lower()
    if suffix == ".json":
        return load_json(path)
    if suffix in (".yaml", ".yml"):
        return load_yaml(path)
    if suffix == ".csv":
        return load_csv(path)
    if suffix == ".xlsx":
        return load_excel(path)
    raise ConfigError(
        f"Unsupported test-data file type '{suffix}' at {path}. "
        f"Expected one of: {', '.join(_CASE_SUFFIXES)}"
    )


def _case_files(directory: Path) -> list[Path]:
    """List a test-data directory's case files in a stable order.

    Sorted so a run's case order — and therefore its report order — doesn't depend on
    filesystem enumeration order. Non-case files (``.gitkeep``, ``README.md``) are
    skipped.

    Args:
        directory: Resolved test-data directory.

    Returns:
        Sorted list of case file paths; empty when the folder holds no case files.
    """
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in _CASE_SUFFIXES
    )


def _to_test_case(path: Path, content: Any) -> TestCase:
    """Wrap one file's parsed content in a :class:`TestCase`.

    Row-oriented files (CSV/Excel) parse to a list rather than a mapping; those are
    wrapped as ``{"rows": [...]}`` so ``test_case.rows`` is how a module reads them and
    the attribute-access contract holds for every format.

    Args:
        path: File the content came from.
        content: Parsed file content.

    Returns:
        The wrapped test case.
    """
    data: dict[str, Any] = content if isinstance(content, dict) else {"rows": content}
    return TestCase(
        name=str(data.get("name") or data.get("case_name") or path.stem),
        description=str(data.get("description") or ""),
        path=path,
        data=data,
    )


def load(
    module_path: str,
    env: str | None = None,
    subsidiary_cd: str | None = None,
    kind: str | None = None,
) -> list[TestCase]:
    """Load every test case for a module in one env/subsidiary/data set.

    This is the data-driven fan-out's input: an orchestrator calls it once and runs one
    concurrent flow per returned case (see docs/context/system-flow.md).

    Args:
        module_path: The module's location under ``lib/app/modules/``, e.g.
            ``"purchase_checker/login"``.
        env: One of "dev", "stg", "prod". Defaults to the run's resolved environment.
        subsidiary_cd: One of the codes in settings.yaml's ``defaults.subsidiaries``,
            e.g. ``"MJP"``. Defaults to the run's resolved subsidiary.
        kind: ``"real"`` or ``"test"`` — which data-character folder to read. Defaults
            to the run's ``DATA_SET``.

    Returns:
        One :class:`TestCase` per case file, in sorted filename order. Empty list when
        the folder exists but holds no case files.

    Raises:
        ConfigError: If the env/subsidiary is unknown, the resolved directory does not
            exist, or a file in it has an unsupported suffix.
    """
    config = get_config(env=env, subsidiary=subsidiary_cd, data_set=kind)
    directory = config.test_data_dir(module_path)
    paths = _case_files(directory)
    if not paths:
        logger.warning("No test-data case files found in %s", directory)
    logger.debug("Loading %d case file(s) from %s", len(paths), directory)
    return [_to_test_case(path, _load_file(path)) for path in paths]


def load_case(module_path: str, name: str) -> dict[str, Any]:
    """Load a single named case file for a module as its raw parsed content.

    Resolves env/subsidiary/data_set from the run's config, so callers name only the
    case. Example: ``load_case("etl/gdb", "happy_path")``.

    Args:
        module_path: The module's location, e.g. ``"etl/gdb"``.
        name: Case file name, with or without its suffix. Without one, the supported
            suffixes are tried in :data:`_CASE_SUFFIXES` order.

    Returns:
        The file's parsed content. Row-oriented formats are wrapped as
        ``{"rows": [...]}`` so the return type is consistent.

    Raises:
        ConfigError: If the directory or the named case does not exist.
    """
    directory = get_config().test_data_dir(module_path)
    candidate = directory / name
    if candidate.suffix.lower() in _CASE_SUFFIXES and candidate.is_file():
        return _to_test_case(candidate, _load_file(candidate)).data

    for suffix in _CASE_SUFFIXES:
        candidate = directory / f"{name}{suffix}"
        if candidate.is_file():
            return _to_test_case(candidate, _load_file(candidate)).data

    available = ", ".join(path.name for path in _case_files(directory)) or "none"
    raise ConfigError(f"Test case '{name}' not found in {directory}. Available: {available}")


def load_all_cases(module_path: str) -> list[dict[str, Any]]:
    """Load every case file in a module's test-data directory as raw dicts.

    The parametrization-friendly counterpart to :func:`load`: same files, without the
    :class:`TestCase` wrapper.

    Args:
        module_path: The module's location, e.g. ``"etl/gdb"``.

    Returns:
        One dict per case file, in sorted filename order.

    Raises:
        ConfigError: If the directory does not exist or holds an unsupported file type.
    """
    return [case.data for case in load(module_path)]
