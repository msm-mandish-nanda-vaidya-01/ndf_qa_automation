# CLAUDE.md — NDF QA Automation

This file is the entry point Claude reads before touching this repo. It defines the rules
that keep the codebase consistent as new modules get added. Detailed reference material lives
in `docs/context/` — read the linked file before doing the related work; don't guess.

## What this project is

A CLI-driven QA automation suite for MISUMI's NDF (Normalized Data File) pipeline ecosystem.
No UI — everything is triggered from an interactive terminal menu. It validates ETL flows and
supporting services (part number rules, replacement matching, admin panel actions, etc.) across
FE (Playwright), BE (httpx), and three storage layers (PostgreSQL, MongoDB/DocumentDB,
OpenSearch) plus S3, across `dev` / `stg` / `prod` and subsidiaries `MJP` / `KOR` / `USA`.

## Before writing any code

This is a mandatory analysis pass, not a suggestion — do this before opening a new file or
adding a function, every time, not just for new modules:

1. **Search before you write.** Grep/read `lib/core/utils/` and `lib/core/db/` for anything that
   already does what you're about to write — URL building, waits/retries, report generation,
   data loading, and all DB client access already live there. If something close-but-not-quite
   exists, extend or parameterize it rather than writing a sibling function. Duplicating these
   is the single most common mistake in this codebase.
2. **Check for an existing pattern in a sibling module.** If you're adding a `be.py`/`fe.py`/
   `db/*_checks.py` to a new module, open an existing module of the same shape (e.g. `etl/gdb`)
   first and match its structure rather than inventing a new one. Divergent patterns across
   modules are a maintenance cost — inconsistency is a bug here, not a style nitpick.
3. **Identify what's actually module-specific vs. shared** before writing. If the logic you're
   about to add doesn't reference this module's specific endpoint/page/table, it's a candidate
   for `lib/core/` instead of living inside the module. Ask yourself: would a second module need
   this unchanged? If yes, it doesn't belong in the module folder.
4. Read `docs/context/system-flow.md` if you're touching orchestrator/be/fe/db wiring.
5. Read `docs/context/test-data-conventions.md` if you're adding or loading test data.
6. Read `docs/context/folder-structure.md` if you're unsure where a new file belongs.
7. If you're scaffolding a brand-new module, use the `new-module-scaffold` skill
   (`.claude/skills/new-module-scaffold/SKILL.md`) instead of hand-rolling the folder. It's
   plan-first: ask which module, plan its Happy path / Error case / Edge case scenarios and
   test-data schema into a `PLAN.md`, confirm that with the user, and only then generate
   orchestrator/be/fe/db and matching test-data skeletons — never generate code for a new
   module before that plan exists and is confirmed.

If, after this pass, you're still about to duplicate something that's 80%+ similar to existing
code, stop and say so explicitly rather than silently writing the duplicate — either the
existing code should be refactored to be reusable, or there's a real reason it needs to differ,
and that reason belongs in a comment.

## Domains

Modules are organized under two domains, each with its own workflow — see
`docs/context/module-workflows.md` for the details of each:

- **`etl`** — pipeline/data-flow modules (e.g. `etl/gdb`).
- **`purchase_checker`** — user-facing search/cross-reference/order flow modules (e.g.
  `purchase_checker/login`). System under test: **XDB Cross** — see
  `docs/context/purchase_checker/xdb_cross_system_flow.md` for the full flow.

Don't add a third top-level domain without updating that file first.

## Architecture (short version — full detail in system-flow.md)

- **orchestrator.py** — defines the flow for its module. Calls `be` → `fe` → `db/*` in order,
  skipping any layer the module doesn't need (e.g. a BE-only module has no `fe.py`). It is also
  the concurrency boundary: for data-driven runs it fans a module's test-data files out in
  parallel (see "Concurrency" below).
- **be.py** — hits the module's specific endpoint(s) via `httpx`, returns the resulting
  state/response. This is the source of truth an `fe.py` check is validated against.
- **fe.py** — drives the specific Admin Panel page via Playwright and asserts the UI reflects
  what `be.py` returned. Never asserts against hardcoded expected values when a BE result is
  available — assert against the BE response.
- **db/*_checks.py** — one file per storage type (`postgres_checks.py`, `mongo_checks.py`,
  `opensearch_checks.py`, `s3_checks.py`). Each verifies persisted state relevant to that module
  only (rows/documents/index entries/S3 keys the module is responsible for). Do not put
  cross-module verification here.

### Cross-module dependencies

If module A needs module B's state as a precondition (e.g. `purchase_checker/login` needs a
logged-in session before another module can act), **A's orchestrator imports B's layers
separately and calls only their designated cross-module entry points**:

| From B | A may call | A must not call |
|---|---|---|
| `be.py` | the entry point that *establishes* state and returns it (`login()`) | anything expecting a specific test outcome (`login_expect_failure()`) |
| `fe.py` | the entry point that *establishes a browser session* and asserts nothing about a scenario (`log_in()`) | the scenario assertion (`assert_matches()`) |
| `db/*_checks.py` | nothing | all of it — B's persisted state is B's suite's business |
| `orchestrator.py` | nothing | all of it — it would run B's whole test suite inside A's run |

The two halves are independent and both are usually wanted: the BE call yields values A
carries forward (a token, an id — `LoginResult.auth_headers()`), while the FE call yields a
live browser session A keeps navigating in. Neither is a substitute for the other — a BE
token does not authenticate a browser, and a browser session is not a request header.

Each imported layer must expose a session/state entry point that is **separate from its
assertion entry point**. A dependent module calling B's assertions would report B's test
outcomes inside A's run and fail A for B's defects; a dependent module hand-stitching B's
internals (`open_login_page` + `submit_credentials`) re-implements B's page sequence and
drifts the moment B's page changes. If B has no such entry point yet, add one to B rather
than inlining B's steps into A.

```python
# inside modules/purchase_checker/some_dependent_module/orchestrator.py
from lib.app.modules.purchase_checker.login import be as login_be
from lib.app.modules.purchase_checker.login import fe as login_fe

async def run(test_case, env, subsidiary_cd, page, config):
    # BE half — state to pass forward. Raises AssertionError if the precondition fails,
    # which aborts this test case (setup failure, per "Error handling" below).
    session = await login_be.login(env, subsidiary_cd)
    headers = session.auth_headers()          # {"Authorization": "Bearer ..."}

    # FE half — a browser session this module continues in. Asserts nothing about login.
    await login_fe.log_in(page, config)

    # proceed with this module's own be/fe/db flow using `headers` and `page`
```

Reuse the FE session rather than logging in per test case: `page.context.storage_state()`
after `log_in` seeds further contexts already authenticated, which keeps a data-driven
fan-out from paying the login cost N times.

### Concurrency

Orchestrators run each test-data file for their module **in parallel** (this is the
"data-driven" fan-out). Use `asyncio` for BE calls (httpx supports async natively) and respect
connection limits:
- Cap concurrent Playwright browser contexts per module run (don't open one per test case
  unbounded — batch with a semaphore; a sane default is 5, tune per module if the Admin Panel
  can't handle more).
- Cap concurrent DB connections via the shared clients in `lib/core/db/` — those clients should
  own their own pool, orchestrators should not open raw connections.
- `pytest-xdist` is for parallelizing across *modules* at the CLI/e2e/critical-path level, not a
  substitute for the per-module async fan-out described above.

## Environments and subsidiaries

- Environments: `dev`, `stg`, `prod`. **Full be→fe→db flow runs in all three** — prod is not
  restricted to read-only. Be deliberate about what actions a prod-facing `be.py` performs;
  don't assume prod safety, verify it per module.
- Subsidiaries: `MJP`, `KOR`, `USA` (add more here as they're onboarded — don't hardcode a list
  elsewhere, read it from `lib/core/config/settings.yaml`).
- Config precedence: non-secret settings (URLs, timeouts, feature flags, env/subsidiary lists)
  live in `lib/core/config/settings.yaml`. Secrets (DB creds, AWS SSO profile, NDF API
  auth) come from `.env.<env>` (`.env.dev` / `.env.stg` / `.env.prod`) via `env_config.py`
  — never hardcode either into module code.

## Test data

See `docs/context/test-data-conventions.md` for the full convention. Short version: test data
lives at `test_data/<module_path>/<env>/<subsidiary_cd>/{real,test}/`, is authored by hand
during development (no fixed cross-module schema — each module defines its own file shape), and
`real` vs `test` means production-like data vs synthetic edge-case data, not "used" vs "draft."
`data_loader.py` resolves the path from `(module_path, env, subsidiary_cd, real|test)` — always
load through it, never build the path manually in a module.

## Error handling & reporting

- On any layer failure (BE, FE, or a specific DB check), **do not short-circuit** — the
  orchestrator keeps running the remaining DB checks for that test case so the failure report
  has full context (what BE returned, what FE showed, what every DB actually persisted), then
  marks the test case failed. Only abort the whole orchestrator run on a setup/precondition
  failure (e.g. the dependency `be.py` call itself fails — there's nothing meaningful left to
  check).
- Retry policy: wrap **BE calls and DB checks that can be eventually-consistent** (OpenSearch
  indexing lag, Mongo/DocumentDB replication lag) in the shared retry helper in
  `lib/core/utils/wait_helper.py` — exponential backoff, small fixed max attempts (default 3),
  logged at WARNING on each retry. Do not add ad-hoc retry loops per module. Playwright FE
  actions rely on Playwright's own auto-waiting; only add an explicit retry for a documented
  flaky interaction, and comment why.
- Allure attachments on failure, generated automatically by `report_generator.py` so modules
  don't hand-roll this: BE request/response JSON, FE screenshot + page URL, and the actual
  query/result dump for whichever DB check failed. Attach all of them, not just the layer that
  failed, so the whole failure context is visible in one place.

## CLI

Interactive terminal menu built with `questionary` (arrow-key select, no memorized flags).
Top-level options: **Module Testing**, **E2E Testing**, **Critical Path Testing**, **Back/Exit**.

- "Module Testing" lists modules by **scanning `lib/app/modules/` at runtime** for leaf
  directories containing an `orchestrator.py` (e.g. `etl/gdb`, `purchase_checker/login`) — never
  maintain a separate static list that can drift from the folder structure.
- Selecting "Back" re-renders the parent menu (no saved navigation state to restore — this is a
  short-lived CLI session, not worth the complexity).
- `main.py` also exposes the same actions via `argparse` flags for CI (`ci.yml` runs non-
  interactively), the interactive menu is for local use.

## Coding standards

- **Docstrings**: Google-style, but written for an LLM reading the file cold — every
  function/module docstring should state *what it does*, *why it exists* (what it's checking or
  producing), *Args*, *Returns*, and *Raises*. Don't assume the reader has the ticket or the
  system-flow doc open.
- **Docstrings are updated in the same change as the logic, always.** If you modify a function's
  behavior, arguments, return shape, exceptions, or the endpoint/table/selector it touches, the
  docstring is not optional cleanup — it's part of the change, not a follow-up. A diff that
  changes what a function does but leaves its docstring describing the old behavior is treated
  as incomplete, the same as missing test coverage would be. This applies to:
  - Any edit to `be.py` / `fe.py` / `db/*_checks.py` / `orchestrator.py` logic.
  - Refactors that move logic between files (update both the old and new location's docstrings —
    don't leave a stale docstring behind on a function that now does less, or delete a docstring
    on a function that now does more).
  - Changes to retry behavior, concurrency limits, or error-handling shape described in a
    docstring's Raises/Returns section.
  - Before finishing any edit, re-read the docstring against the new code and fix any mismatch —
    don't wait to be asked.
- **Type hints everywhere**: every function signature (params and return type) gets type hints.
  This codebase relies on hints instead of runtime shape-checking in most places — an untyped
  `def run(test_case, env, subsidiary_cd)` is treated as incomplete, not just unpolished.
- **Naming**: match the vocabulary already in the codebase — `env`, `subsidiary_cd`, `test_case`,
  `be_result` are the established names for these concepts; don't rename them per-module (e.g.
  don't introduce `country_code` alongside `subsidiary_cd` for the same thing). Function names
  describe the action (`verify`, `assert_matches`, `run`), not the implementation detail.
- **Function size and single responsibility**: a function that does BE-call-then-DB-check-then-
  logging-then-retry in one body is a sign it should be split — retries belong in
  `wait_helper`, logging is a cross-cutting concern threaded through, not folded into business
  logic. If a function's docstring needs "and" more than once to describe what it does, split it.
- **No duplication across be/fe/db-check files**: if two `db/*_checks.py` files (in the same or
  different modules) end up with near-identical query-building or comparison logic, that logic
  belongs in `lib/core/db/` or `lib/core/utils/`, not copy-pasted. Same for `be.py` files that
  both build similar request payloads — factor the shared shape out.
- **No hardcoded env/subsidiary/URL/credential values** in module code — these always come from
  `settings.yaml` / `env_config.py` via the helpers, never inlined as string literals in a
  `be.py` or `fe.py`. This is both a duplication issue and a security one (see `.env` handling).
- **Assert against BE results, not hardcoded expectations**, wherever a BE call already produced
  the expected value (see `fe.py` and `db/*_checks.py` conventions above) — a second hardcoded
  "expected" value is both duplication and a second source of truth that can drift. For modules
  where no live BE result exists to compare against (e.g. pure validation-logic checks), the
  expected value instead comes from the test-data file itself — either hardcoded or resolved
  from the DB/backend at run time — per `docs/context/test-data-conventions.md`.
- **Logging**: standard `logging` module. Console handler (INFO+) and a per-run file handler
  writing to `logs/<suite>_<env>_<subsidiary_cd>_<data_set>_<timestamp>.log` (DEBUG+) — the
  timestamp is what keeps each run's file separate, since the handler appends. Levels: DEBUG = raw
  request/response payloads and DB queries, INFO = flow milestones (orchestrator/be/fe/db
  start/end per test case), WARNING = retries, ERROR = a layer failed for a test case, CRITICAL
  = orchestrator aborted the whole run.
- **Formatting/linting**: black/ruff/isort via `pyproject.toml` and `.pre-commit-config.yaml` —
  run `make lint` before committing. Ruff's unused-import/unused-variable checks are a proxy for
  leftover copy-paste — don't suppress them without a reason.

### Self-check before considering code done

Before treating a change as finished, confirm all of these — don't just eyeball it:

- [ ] Did a search of `lib/core/` for existing logic before writing anything new (see "Before
      writing any code" above), and can point to what was checked if asked.
- [ ] No function/module lacks a docstring; no function signature lacks type hints.
- [ ] For every function touched in this diff, the docstring was re-read against the new logic
      and updated if behavior, Args, Returns, or Raises changed — not left describing old code.
- [ ] No env/subsidiary/URL/credential literal is hardcoded in the diff.
- [ ] No block of logic in this diff closely resembles a block elsewhere in the repo without a
      documented reason for the difference.
- [ ] Logging calls are at the levels defined above, not ad hoc.
- [ ] `make lint` passes.

## Reference index

| Need to... | Read |
|---|---|
| Run the suite, change a run parameter, or view a report | `docs/setup/running-tests.md` |
| Understand how orchestrator/be/fe/db fit together, or wire a new module | `docs/context/system-flow.md` |
| Add or load test data, or decide where an expected value comes from | `docs/context/test-data-conventions.md` |
| Find where a file belongs | `docs/context/folder-structure.md` |
| Understand the `etl` vs `purchase_checker` domain workflows | `docs/context/module-workflows.md` |
| Understand XDB Cross (the system `purchase_checker` tests) call-by-call | `docs/context/purchase_checker/xdb_cross_system_flow.md` |
| See what context is still missing before scaffolding | `docs/context/module-workflows.md` → "Known gaps" |
| Scaffold a new module from scratch | `.claude/skills/new-module-scaffold/SKILL.md` |
