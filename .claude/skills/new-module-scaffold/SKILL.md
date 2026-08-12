---
name: new-module-scaffold
description: Scaffold a new NDF QA automation module (orchestrator.py, be.py, fe.py, db/*_checks.py, and its test_data folders) following this repo's conventions. Use this whenever the user asks to add a new module, add a new test target, wire up testing for a new endpoint/page/pipeline step, or says things like "create a module for X", "add a new orchestrator for X", "set up be/fe/db for X". Always use this instead of hand-writing the files from scratch — it plans the module's scenarios and test-data schema into a PLAN.md first, then generates code and test-data skeletons from that plan, keeping docstring style, logging, error handling, and the be/fe/db-skip rules consistent across the codebase.
---

# New Module Scaffold

Generates a new module under `lib/app/modules/<domain>/<module_name>/` with the
orchestrator/be/fe/db shape this repo standardizes on, plus its `test_data/` folders.
Read `docs/context/system-flow.md`, `docs/context/test-data-conventions.md`, and
`docs/context/module-workflows.md` first if you haven't already this session — this skill
assumes those conventions, and `<domain>` must be one of the two domains defined in
`module-workflows.md` (`etl` or `purchase_checker`).

**Nothing is generated before a `PLAN.md` exists and the user has confirmed it.** This
skill is plan-first: Steps 1–3 are entirely Q&A and end in a written plan; Steps 4–6 only
execute after that plan is confirmed. Don't skip ahead to generating files because the
answers "seem obvious" — the plan file is what makes later development and test-data
authoring traceable, and skipping it defeats the point of this skill.

## Step 1: Ask which module the user wants to develop

Before anything else, ask directly — don't infer this from prior conversation context
even if it seems implied:

1. **Domain and name** → determines the path: `lib/app/modules/<domain>/<module_name>/`
   (e.g. `domain=etl, module_name=gdb` → `lib/app/modules/etl/gdb/`). `<domain>` must be
   `etl` or `purchase_checker` — see `docs/context/module-workflows.md`. If `domain=purchase_checker`,
   also read `docs/context/purchase_checker/xdb_cross_system_flow.md` first and confirm with
   the user which flow node(s) (`S`/`N` identifier) this module covers — that mapping isn't
   established anywhere yet (see module-workflows.md's "Known gaps"), so don't infer it.

## Step 2: Confirm the module's shape

1. **Which layers does this module actually need?**
   - BE only (no UI surface to check)?
   - BE + FE (no persisted state worth checking, or covered by another module's `db/*`)?
   - BE + FE + DB (full flow)? Which DB(s) specifically — not all four are always relevant,
     and there are two distinct Postgres databases (`postgres_gdb`, `postgres_repl`) — confirm
     which one, don't assume.
   - Do **not** create a stub file for a layer the module doesn't use. An absent file is the
     correct signal, per `system-flow.md`.
2. **Does this module depend on another module's state?** If yes, which module, and which
   halves it needs: the dependency's `be.py` for state to carry forward, and/or its `fe.py`
   for an authenticated browser session. Confirm each call goes through that layer's
   state-establishing entry point (`be.login()` / `fe.log_in()`), never its assertion entry
   point, and never the dependency's `db/*` or `orchestrator.py` — see system-flow.md's
   "Cross-module dependencies" section. If the dependency has no such entry point, add one
   there rather than inlining its steps here.
3. **Which environments/subsidiaries** does this module apply to? (Default: all of
   `dev/stg/prod` × `MJP/KOR/USA` unless the user says otherwise — some modules are
   subsidiary-specific.)
4. **Where does the expected value come from for this module's checks** (see
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

## Step 3: Plan the scenarios and test-data schema, then write PLAN.md

This is the step that produces the plan file — don't jump to Step 4 without it.

1. **Ask the user for the test-data structure**: what fields does one test case need, and
   what does each mean? (Input fields for `be.py`, plus, per Step 2's answer, either nothing
   further — live `be_result` mode — or an `expected`-shaped field.) Write these into the
   plan's schema table.
2. **Ask the user to enumerate scenarios in three categories** — don't invent these yourself,
   they come from the user's knowledge of the module's real behavior:
   - **Happy path** — the normal, successful case(s).
   - **Error cases** — invalid input, rejected requests, permission failures — anything the
     module should handle as a deliberate failure, not a bug.
   - **Edge cases** — boundary values, empty/null fields, unusual-but-valid input, race/
     timing conditions worth covering.
   At least one scenario per category is expected unless the user says a category genuinely
   doesn't apply to this module (e.g. a read-only module may have no meaningful error case) —
   confirm that explicitly rather than silently leaving a category empty.
3. **Write `lib/app/modules/<domain>/<module_name>/PLAN.md`** from
   `assets/plan_template.md`, filling in every section with Steps 1–3's answers: module
   identity, layers, environments/subsidiaries, expected-value source, the schema table, and
   one row per scenario under Happy path / Error cases / Edge cases. Each scenario row's `File`
   column is the test-data file that scenario will become in Step 5 — name it per
   `test-data-conventions.md` now, since Step 5 generates exactly these files.
4. **Show the compiled plan to the user and confirm it before proceeding.** Treat this the
   same as any other checkpoint before doing generation work — a plan the user didn't actually
   review produces the same "dead stub" problem this skill exists to avoid, just one level up.
   Mark the plan's Status as `confirmed` once they agree; only then move to Step 4.

## Step 4: Generate the code files

Use the templates in `assets/` as the starting point, filling in the module name, domain, and
only the layers confirmed in Step 2 — read them from the now-confirmed `PLAN.md`, not from
memory of the conversation. Templates already include:
- Google-style, LLM-friendly docstrings (what/why/Args/Returns/Raises) — fill in the specifics,
  don't strip the structure. Reference `PLAN.md` in the module docstring (e.g. "see PLAN.md for
  the full scenario and schema decisions") so the next reader finds the plan, not just the code.
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
├── PLAN.md               (assets/plan_template.md — written in Step 3, already confirmed)
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

## Step 5: Generate the test_data skeleton files from the plan

Unlike ad hoc scaffolding, this skill does not leave `test_data/` empty. For each
`(env, subsidiary_cd)` combination confirmed in Step 2, and for **every scenario row in
PLAN.md's Section 6**, create the corresponding file under:
```
test_data/<domain>/<module_name>/<env>/<subsidiary_cd>/{real,test}/<file from PLAN.md>
```
using the exact file name from the plan and the field shape from the plan's schema table,
populated with clearly-marked placeholder values (e.g. `"TODO: replace with real value"`)
rather than invented realistic data — the plan fixes the *shape* and *which scenarios exist*,
not the real content. Authoring real content is a separate, later pass per
`test-data-conventions.md`, done by the user (or on separate request).

Whether a given scenario's file goes under `real/` or `test/` follows
`test-data-conventions.md`'s data-character split (production-like vs. synthetic edge case) —
ask the user per scenario if it's not obvious from the category (most Happy-path scenarios
using representative data lean `real/`; most Error/Edge scenarios lean `test/`, but this isn't
a fixed rule).

## Step 6: Register nothing manually

The CLI discovers modules by scanning `lib/app/modules/` for directories containing
`orchestrator.py` at runtime (see root `CLAUDE.md`, "CLI" section) — there is no registry file
to update. Confirm the new `orchestrator.py` exists and exposes a `run(...)` entry point
matching the signature other modules use, and it will appear in the menu automatically.

## Step 7: Summarize back to the user

State plainly: where `PLAN.md` lives (that's the reference for everything decided), which
files were created, which layers were skipped and why, whether a dependency call was wired
in, which expected-value mode was used, and how many scenario skeleton files were generated
per category. Don't ask the user to double check routine parts (naming, docstrings) — call
those out only if something in Steps 1–3 was genuinely ambiguous and you made a judgment call.
