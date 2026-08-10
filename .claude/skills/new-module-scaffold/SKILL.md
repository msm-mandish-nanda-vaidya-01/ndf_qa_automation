---
name: new-module-scaffold
description: Scaffold a new NDF QA automation module (orchestrator.py, be.py, fe.py, db/*_checks.py, and its test_data folders) following this repo's conventions. Use this whenever the user asks to add a new module, add a new test target, wire up testing for a new endpoint/page/pipeline step, or says things like "create a module for X", "add a new orchestrator for X", "set up be/fe/db for X". Always use this instead of hand-writing the files from scratch — it keeps docstring style, logging, error handling, and the be/fe/db-skip rules consistent across the codebase.
---

# New Module Scaffold

Generates a new module under `lib/app/modules/<domain>/<module_name>/` with the
orchestrator/be/fe/db shape this repo standardizes on, plus its `test_data/` folders.
Read `docs/context/system-flow.md`, `docs/context/test-data-conventions.md`, and
`docs/context/module-workflows.md` first if you haven't already this session — this skill
assumes those conventions, and `<domain>` must be one of the two domains defined in
`module-workflows.md` (`etl` or `purchase_checker`).

## Step 1: Ask what the module needs (don't guess)

Before generating anything, confirm with the user:

1. **Domain and name** → determines the path: `lib/app/modules/<domain>/<module_name>/`
   (e.g. `domain=etl, module_name=gdb` → `lib/app/modules/etl/gdb/`). `<domain>` must be
   `etl` or `purchase_checker` — see `docs/context/module-workflows.md`. If `domain=purchase_checker`,
   also read `docs/context/purchase_checker/xdb_cross_system_flow.md` first and confirm with
   the user which flow node(s) (`S`/`N` identifier) this module covers — that mapping isn't
   established anywhere yet (see module-workflows.md's "Known gaps"), so don't infer it.
2. **Which layers does this module actually need?**
   - BE only (no UI surface to check)?
   - BE + FE (no persisted state worth checking, or covered by another module's `db/*`)?
   - BE + FE + DB (full flow)? Which DB(s) specifically — not all four are always relevant.
   - Do **not** create a stub file for a layer the module doesn't use. An absent file is the
     correct signal, per `system-flow.md`.
3. **Does this module depend on another module's state?** If yes, which module, and confirm
   the dependency call goes through the dependency's `be.py` only (never its `fe.py`, `db/*`,
   or `orchestrator.py` — see system-flow.md's "Cross-module dependencies" section).
4. **Which environments/subsidiaries** does this module apply to? (Default: all of
   `dev/stg/prod` × `MJP/KOR/USA` unless the user says otherwise — some modules are
   subsidiary-specific.)
5. **Where does the expected value come from for this module's checks** (see
   `docs/context/test-data-conventions.md`, "Where the 'expected result' comes from")?
   - Live `be_result` (default whenever `be.py` produces the state under test)?
   - Test-data-defined instead, because there's no live `be_result` to check against — and if
     so, is that expected value **hardcoded** in the test-data file, or **resolved from the
     DB/backend at run time** by this module's own code?
   This determines whether the generated `fe.py`/`db/*_checks.py` bodies reference `be_result`
   or `test_case.expected`, and whether any DB/backend-lookup helper needs wiring in.

If any of this is ambiguous from what the user already said, ask — don't default to "full
flow, all envs" or "live BE result" silently, since that generates dead stub files or checks
against the wrong source of truth.

## Step 2: Generate the files

Use the templates in `assets/` as the starting point, filling in the module name, domain, and
only the layers confirmed in Step 1. Templates already include:
- Google-style, LLM-friendly docstrings (what/why/Args/Returns/Raises) — fill in the specifics,
  don't strip the structure.
- Logging calls at the right levels (INFO for flow milestones, DEBUG for payloads/queries,
  WARNING for retries, ERROR for failures) via `lib.core.config.logging_config`.
- Retry wrapping (`wait_helper`) already applied to the BE call template and to DB check
  templates for OpenSearch/Mongo — leave in place, don't add ad hoc retry logic.
- The "don't short-circuit on failure" pattern in the orchestrator template — all confirmed
  layers run even if an earlier one fails, and the precondition/dependency call is the only
  thing that short-circuits.

Files to create (only for confirmed layers):
```
lib/app/modules/<domain>/<module_name>/
├── __init__.py
├── orchestrator.py      (assets/orchestrator_template.py)
├── be.py                (assets/be_template.py)
├── fe.py                (assets/fe_template.py, only if FE confirmed)
└── db/
    ├── __init__.py
    ├── postgres_checks.py    (assets/db_check_template.py, only if confirmed)
    ├── mongo_checks.py       (assets/db_check_template.py, only if confirmed)
    ├── opensearch_checks.py  (assets/db_check_template.py, only if confirmed)
    └── s3_checks.py          (assets/db_check_template.py, only if confirmed)
```

## Step 3: Create the test_data folders

For each `(env, subsidiary_cd)` combination confirmed in Step 1, create:
```
test_data/<domain>/<module_name>/<env>/<subsidiary_cd>/real/
test_data/<domain>/<module_name>/<env>/<subsidiary_cd>/test/
```
Leave these empty (or with a `.gitkeep`) — actual test-data files are authored by the user per
`test-data-conventions.md`, not generated by this skill. Do not invent placeholder CSVs/JSONs
unless the user explicitly asks for example data to start from.

## Step 4: Register nothing manually

The CLI discovers modules by scanning `lib/app/modules/` for directories containing
`orchestrator.py` at runtime (see root `CLAUDE.md`, "CLI" section) — there is no registry file
to update. Confirm the new `orchestrator.py` exists and exposes a `run(...)` entry point
matching the signature other modules use, and it will appear in the menu automatically.

## Step 5: Summarize back to the user

State plainly: which files were created, which layers were skipped and why, whether a
dependency call was wired in, and which expected-value mode was used (live `be_result`,
hardcoded test-data, or DB/backend-resolved test-data) — all based on Step 1's answers. Don't
ask the user to double check routine parts (naming, docstrings) — call those out only if
something in Step 1 was genuinely ambiguous and you made a judgment call.
