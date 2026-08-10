# Test Data Conventions

Read this before adding test data for a module, or writing/modifying code that loads it
(`lib/core/utils/data_loader.py` and anything that calls it).

## Path convention

```
test_data/<module_path>/<env>/<subsidiary_cd>/{real,test}/
```

- `<module_path>` mirrors the module's location under `lib/app/modules/` (e.g. `etl/gdb`,
  `purchase_checker/login`).
- `<env>` is one of `dev`, `stg`, `prod`.
- `<subsidiary_cd>` is one of `MJP`, `KOR`, `USA` (extend as new subsidiaries onboard — keep the
  authoritative list in `lib/core/config/settings.yaml`, not hardcoded in loader code).
- `real/` vs `test/`:
  - **`real/`** — production-like data, structurally and semantically representative of what
    actually flows through the pipeline for that subsidiary/env.
  - **`test/`** — synthetic data written specifically to exercise edge cases (boundary values,
    malformed inputs, the specific bug conditions a ticket describes).
  - Both are "real" test suites in the QA sense — this split is about data *character*, not
    about draft vs. final.

## Schema is per-module, by design

There is **no single fixed schema** across all modules' test data — each module's `be.py` /
`fe.py` defines what its own test-data files need to contain, and that shape is authored by
hand during development of that module, not generated from a shared template. (This is
different from the separate `ndf-3-test-files-creation` skill, which produces the specific
3-file GDB/Spec Grouping/Type Grouping set used as *pipeline input* — that's upstream of this
automation repo, not the same thing as a module's test-data fixtures here.)

## Where the "expected result" comes from

A test case needs two things: input to feed `be.py`, and something to check the outcome
against. Which source that check runs against is decided **per module, during that module's
development**, and falls into one of two modes — document which mode a module uses in that
module's own docstring or a short `README.md` alongside its test data:

1. **Live BE result (preferred, default)** — when `be.py` itself performs the action under
   test in the same run (e.g. it POSTs and the response *is* the resulting state), `fe.py` and
   `db/*_checks.py` assert against that live `be_result`, not against anything stored in the
   test-data file. This is the existing rule in `system-flow.md` / `CLAUDE.md` ("assert against
   BE results, not hardcoded expectations") and takes precedence whenever a live `be_result` for
   that test case exists — a hardcoded value duplicating it is still a second source of truth
   that can drift, even under mode 2 below.
2. **Test-data-defined expected value** — used when there's no live `be_result` to compare
   against for the thing being checked (e.g. a pure validation-logic module like
   `part_number_rules`, where the input already has a predetermined correct answer; or a
   read-only check against pre-existing prod-like state). Within this mode, the expected value
   itself can be either:
   - **Hardcoded** — written literally into the test-data file by whoever authored the
     scenario (e.g. `"expected_valid": false` next to a malformed part number).
   - **Retrieved at run time from the DB/backend** — the test-data file holds a reference/query
     (e.g. a part number to look up) rather than a literal expected value, and the module's
     `be.py` or a `db/*_checks.py` resolves the actual expected value from Postgres/Mongo/the
     API before comparing. This resolution logic lives in the module's own code, never in
     `data_loader.py` — the loader only parses whatever fields exist in the file into the
     `test_case` object; it doesn't know how to interpret an `expected` field for any given
     module.

   Which of these two (hardcoded vs. retrieved) a module uses, and the exact field name/shape
   for its expected value, is decided during that module's development along with the rest of
   its schema — call it out in the module's docstring the same way the input schema is called
   out.

When adding test data for a module:
- Name files so a failure report is traceable back to intent, e.g.
  `NDFDPAPJ-1856_and_or_precedence.csv` or `login_invalid_credentials.json` — include the ticket
  ID or a descriptive scenario tag, not just `test1.csv`.
- Document the shape you chose in that module's own docstring (in `be.py` or a short
  `README.md` alongside the module if the shape isn't obvious from the file itself) — the next
  person (or Claude) reading only the test-data folder should be able to tell what a file
  represents without opening `be.py`.
- Keep one file = one scenario where practical; don't bundle unrelated scenarios into one file
  just to reduce file count — it breaks the data-driven fan-out (see system-flow.md), which
  parallelizes per file.

## Loading test data

Always resolve paths through `lib/core/utils/data_loader.py` — never build
`test_data/...` paths by hand inside a module. The loader's job is:

```python
data_loader.load(module_path: str, env: str, subsidiary_cd: str, kind: Literal["real", "test"])
# -> yields one parsed test case per file found in that folder
```

This keeps the path convention in exactly one place, so if it ever changes, modules don't need
touching.
