# Plan: <DOMAIN>/<MODULE_NAME>

Filled in during Steps 1–3 of the `new-module-scaffold` skill, **before any code or
test-data file is generated**. This is the single source of truth for what this module
does, what it tests, and how — code/test-data generation in later steps reads from
this file, and it's updated first if any of these decisions change later.

Status: <draft | confirmed | implemented>

## 1. Module identity

- Domain: `<etl | purchase_checker>`
- Module name: `<module_name>`
- Path: `lib/app/modules/<domain>/<module_name>/`
- Purchase Checker flow node(s) (purchase_checker modules only — see
  `docs/context/purchase_checker/xdb_cross_system_flow.md`): `<S#/N# or N/A>`
- Depends on another module's state?: `<none | <domain>/<module>, via its be.py only>`

## 2. Layers in use

- [ ] BE (`be.py`) — endpoint(s): `<...>`
- [ ] FE (`fe.py`) — Admin Panel page/selectors: `<...>`
- [ ] DB — which stores:
  - [ ] `postgres_gdb`
  - [ ] `postgres_repl`
  - [ ] `mongo`
  - [ ] `opensearch`
  - [ ] `s3`

An unchecked layer gets no file for this module — an absent file is the correct
signal (see `docs/context/system-flow.md`), not a stub raising `NotImplementedError`.

## 3. Environments & subsidiaries

- Environments: `<dev/stg/prod or subset>`
- Subsidiaries: `<MJP/KOR/USA or subset>`

## 4. Expected-value source

(See `docs/context/test-data-conventions.md`, "Where the 'expected result' comes from".)

- [ ] Live `be_result` (default — use this whenever `be.py` produces the state under test)
- [ ] Test-data-defined — hardcoded literally in the test-data file
- [ ] Test-data-defined — resolved from the DB/backend at run time by this module's own code

## 5. Test data schema

Fields every test-data file for this module contains, confirmed with the user before
any file is generated:

| Field | Type | Meaning |
| --- | --- | --- |
| `name` | string | scenario name — should match the file name |
| `...` | `...` | `...` |

## 6. Scenarios

One row = one planned test-data file, at
`test_data/<domain>/<module_name>/<env>/<subsidiary>/{real,test}/<file>`. File naming
follows `docs/context/test-data-conventions.md` — a ticket ID or descriptive scenario
tag, never `test1.json`. `real/` vs `test/` per file follows the same doc's data-character
split (production-like vs. synthetic edge case), not this table's category.

### Happy path

| File | Description | Expected outcome |
| --- | --- | --- |
| `<name>.json` | `<...>` | `<...>` |

### Error cases

| File | Description | Expected outcome |
| --- | --- | --- |
| `<name>.json` | `<...>` | `<...>` |

### Edge cases

| File | Description | Expected outcome |
| --- | --- | --- |
| `<name>.json` | `<...>` | `<...>` |

## 7. Status checklist

- [ ] Plan confirmed with the user (Step 3)
- [ ] Code generated: orchestrator/be/fe/db (Step 4)
- [ ] Test-data skeleton files generated, matching Section 6 (Step 5)
- [ ] Real test-data content authored — the skill only generates skeletons/placeholders;
      filling in real values per `test-data-conventions.md` is a separate, later pass
