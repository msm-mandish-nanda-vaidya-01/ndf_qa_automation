# System Flow

How a single module executes, end to end. Read this before writing or modifying an
`orchestrator.py`, `be.py`, `fe.py`, or any `db/*_checks.py`.

## The four layers

```
orchestrator.py
      │
      ├── be.py           (httpx)        → hits the module's endpoint(s), returns response/state
      ├── fe.py           (Playwright)   → drives the Admin Panel page, asserts UI == be.py result
      └── db/
           ├── postgres_checks.py        → verifies rows this module is responsible for
           ├── mongo_checks.py           → verifies documents this module is responsible for
           ├── opensearch_checks.py      → verifies index entries this module is responsible for
           └── s3_checks.py              → verifies S3 keys this module is responsible for
```

A module may skip any layer it doesn't need. Examples:
- A pure data-import module might have `be.py` + `db/*` only, no `fe.py` (nothing to check in
  the UI).
- A UI-only cosmetic check might have `fe.py` + a thin `be.py` to set up state, no `db/*`.

Don't add a stub file for a layer a module doesn't use — an absent file *is* the signal that
layer isn't relevant, not an oversight to "complete."

## Orchestrator responsibilities

`orchestrator.py` is the only place that knows the *order* of calls for its module. Concretely,
for one test case it should:

1. Resolve and load the test case's data via `lib/core/utils/data_loader.py`.
2. Resolve any cross-module dependency (see below) to get preconditions in place.
3. Call `be.py` for this module, capture the response/state.
4. If `fe.py` exists for this module, call it with the BE result as the expected value to
   assert against (not a hardcoded expectation baked into the test data).
5. Run every `db/*_checks.py` file that exists for the module — **all of them, even if an
   earlier layer already failed** — to gather full failure context in one report.
6. Hand everything (BE result, FE result, all DB results, exceptions) to
   `lib/core/utils/report_generator.py`, which formats and attaches to Allure.

For a *data-driven* run (multiple test-data files/cases for the module), the orchestrator
fans step 1–6 out concurrently across test cases — see "Concurrency" below — rather than
looping sequentially.

## Cross-module dependencies

When module A needs state that module B is responsible for creating (most commonly: A needs a
logged-in session that `purchase_checker/login` produces), **A's orchestrator imports and calls
only B's `be.py`**:

```python
from lib.app.modules.purchase_checker.login import be as login_be

session_state = await login_be.login(env, subsidiary_cd, credentials)
```

Rules for this:
- Never call B's `fe.py` or `db/*` from A — B's own test suite already covers that; re-running
  it from A is duplicated work and duplicated failure noise.
- Never call B's `orchestrator.py` from A — the orchestrator layer is for *running that
  module's own test cases*, not for reuse as a setup step.
- If the dependency's `be.py` call itself fails, treat it as a precondition failure: abort that
  test case immediately (don't run A's own be/fe/db — there's nothing meaningful to check yet),
  log at ERROR, and report it distinctly from a normal assertion failure so it's not confused
  with a bug in module A.

## Concurrency model

Two independent axes of parallelism exist in this repo — don't conflate them:

1. **Within a module, across test cases** (the "data-driven" fan-out): the orchestrator uses
   `asyncio` to run multiple test-data files concurrently, since `be.py` is httpx/async-native.
   Guardrails:
   - Playwright browser contexts: bound with an `asyncio.Semaphore` (default cap: 5 concurrent
     contexts per module run — raise only if the Admin Panel environment can take it).
   - DB connections: never opened ad hoc inside a test case — always go through the pooled
     clients in `lib/core/db/` (`postgres_client.py`, `mongo_client.py`, `opensearch_client.py`),
     which own their own connection pool sized independently of test-case concurrency.
2. **Across modules/suites**, at the `e2e`/`critical_path` orchestrator level or in CI: this is
   `pytest-xdist` process-level parallelism. It's orthogonal to (1) — xdist parallelizes whole
   pytest sessions/modules, it does not replace the async fan-out inside a single module.

## Error handling contract

- A layer failing (BE call raises, FE assertion fails, one DB check fails) does not stop the
  remaining layers for **that test case** from running — full failure context matters more than
  fast-fail here. It does mark the test case as failed overall.
- A precondition/dependency failure (see above) *does* short-circuit that test case, since
  there's no valid state left to check.
- Retries live in `lib/core/utils/wait_helper.py` and are applied to: BE calls, and DB checks
  against eventually-consistent stores (OpenSearch indexing lag, Mongo/DocumentDB replication
  lag). Default: exponential backoff, 3 attempts max, WARNING-level log per retry. Playwright
  FE steps rely on Playwright's built-in auto-waiting; add an explicit retry only for a
  documented flaky interaction, with a comment explaining why.
- Every failure attaches, via `report_generator.py`, to Allure: the BE request/response, the FE
  screenshot + URL (if `fe.py` ran), and the query/result for every DB check that ran — not just
  the one that failed.
