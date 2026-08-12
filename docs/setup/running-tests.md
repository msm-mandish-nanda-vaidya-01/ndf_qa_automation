# Running the suite

Day-to-day command reference: how to launch a run, every parameter you can change and
where it lives, and how to read the results. First clone? Do
[`getting-started.md`](getting-started.md) first — this file assumes `.env.dev` exists
and dependencies are installed.

## Current state — read this first

The suite is partially implemented. What actually runs today:

| Target | State |
| --- | --- |
| `purchase_checker/login` | **Implemented end to end** (BE + FE). This is the only module that runs. |
| `etl/gdb` | Collects, but every test body raises `NotImplementedError` |
| `lib/app/e2e/`, `lib/app/critical_path/` | Same — placeholders |
| `python -m lib.app.main.main` (the CLI) | **Not implemented** — raises `NotImplementedError`. The interactive `questionary` menu described in `CLAUDE.md` doesn't exist yet. |
| `make …` targets | The `Makefile` exists, but **`make` is not installed on the current dev machine**. Treat its targets as documentation and run the underlying `python -m pytest` commands. |

So `pytest` is the interface. `python -m pytest` with no arguments now collects **252**
tests, because every test runs once per env × subsidiary × data-set combination (see
[CLI flags](#1-cli-flags--the-run-target)). That resolves to 6 real runs of
`purchase_checker/login`, 120 skips for combinations with no test data authored, and 126
errors from the `e2e` / `critical_path` placeholders — the same `NotImplementedError`
stubs as before, now reported per combination. Expected, not a broken install.

## Quick start

```bash
python -m pytest -m module lib/app/modules/purchase_checker/login \
    --env dev --subsidiary MJP --data-set test
```

All three flags are optional, **and omitting one means "every value"**, not "a default
one" — so the command above narrows a matrix rather than picking the only target:

```bash
# Everything: 3 envs x 3 subsidiaries x 2 data sets = 18 combinations
python -m pytest -m module lib/app/modules/purchase_checker/login

# Several values per flag — repeat it, or comma-separate. These are identical:
python -m pytest … --env dev --env stg
python -m pytest … --env dev,stg

# Mix and match: two envs, one subsidiary, both data sets
python -m pytest … --env dev,stg --subsidiary MJP
```

Each combination is a separate parametrized test — `test_login_module[dev-MJP-test]` —
so one command reports pass/fail per combination instead of stopping at the first. Values
are case-insensitive (`--env DEV`, `--subsidiary mjp`), duplicates collapse, and the run
order follows `settings.yaml` regardless of the order you type them in.

See [Precedence](#precedence) for how this interacts with `$ENV`/`$SUBSIDIARY`/`$DATA_SET`.

## Modifiable parameters

There are four places a parameter can live. Which one you reach for depends on whether
the value is a **run target** (CLI), a **secret** (`.env.<env>`), **non-secret config**
(`settings.yaml`), or a **module constant** (code).

### 1. CLI flags — the run target

Registered in `lib/core/fixtures/conftest.py`.

All three are repeatable and comma-separated, and default to **all** of their values.

| Flag | Values | Omitted | Meaning |
| --- | --- | --- | --- |
| `--env` | `dev` \| `stg` \| `prod` | all three | Selects `.env.<env>` and the `environments.<env>` block of `settings.yaml` |
| `--subsidiary` | `MJP` \| `KOR` \| `USA` | all configured | Selects the `*_<SUB>` credential set. Must appear in `settings.yaml`'s `defaults.subsidiaries` |
| `--data-set` | `real` \| `test` | both | Selects `test_data/<module>/<env>/<sub>/{real,test}/` |

A combination reached only by that expansion is **skipped** when the module has no test
data authored for it, with the missing path as the reason — that's why a bare `pytest`
against `purchase_checker/login` reports 6 run and 12 skipped rather than 12 failures. Name
a combination explicitly and it is never skipped: `--env stg` errors with
`Test data directory does not exist`, because asking for something unauthored is a mistake
worth seeing rather than hiding.

**`--data-set` is the flag people trip over.** It decides which scenarios run:

| Value | For `purchase_checker/login` | Writes a token? |
| --- | --- | --- |
| `test` | the 6 negative scenarios | No |
| `real` | the happy path | **Yes** — `BE_API_TOKEN_<SUB>` in `.env.<env>` |

Standard pytest flags also apply — the ones that matter here:

```bash
-m "module and be"    # marker filter: module, e2e, critical_path, be, fe, db,
                      # postgres, mongo, opensearch, s3, slow  (--strict-markers is on)
-k valid_login        # substring match on test name
-q / -v               # quieter / louder
-x                    # stop at first failure
--timeout=600         # override the 300s default from pytest.ini (see the note below)
--log-cli-level=DEBUG # stream DEBUG to the console, not just the log file
-n auto               # pytest-xdist. Intended for parallelising across *modules*;
                      # untested against this module, which already fans out internally
```

> **`--timeout`**: `pytest.ini` sets `--timeout=300`. An orchestrator runs *all* of a
> module's test cases inside one pytest test, so the limit applies to the whole batch,
> not per scenario. Six login scenarios finish well inside it; a module with many
> test-data files may need this raised.

### 2. `.env.<env>` — secrets and run defaults

Never committed. `env_config.py` picks the file matching `ENV`.

| Key | Purpose |
| --- | --- |
| `ENV` | Default environment when `--env` is omitted |
| `DATA_SET` | Default data set when `--data-set` is omitted |
| `FE_URL_<SUB>` | Per-subsidiary frontend base URL, **including the locale path** (`…/ja/`, `…/ko/`, `…/en_US/`). Both the BE login endpoint and the FE entry point derive from this — the locale is read off it, so there is no separate subsidiary→locale map |
| `FE_USERNAME_<SUB>` / `FE_PASSWORD_<SUB>` | Login credentials. **Valid credentials live only here**, never in test data |
| `BE_API_TOKEN_<SUB>` | Bearer token. Hand-editing is pointless for login — a `--data-set real` run overwrites it |
| `POSTGRES_*_GDB` / `POSTGRES_*_REPL`, `MONGO_*`, `OPENSEARCH_*`, `AWS_*` | Datastore access. Unused by `purchase_checker/login` |

There is no `SUBSIDIARY` key in the shipped files — set it as a real environment
variable or pass `--subsidiary`.

> **Config is validated eagerly and as a whole.** `get_config()` resolves every section —
> Postgres, Mongo, OpenSearch, AWS, and the `certs/` paths — before any test runs, even
> for a module that touches none of them. A cert file named in `.env.<env>` but missing
> from `certs/` therefore blocks the run outright. `purchase_checker/login` only needs
> `FE_URL_<SUB>`, `FE_USERNAME_<SUB>` and `FE_PASSWORD_<SUB>` to be *correct*, but the
> rest of the file still has to be *resolvable*.

### 3. `lib/core/config/settings.yaml` — non-secret config

`defaults` is deep-merged with `environments.<env>`, so an environment block overrides
only the keys it names.

| Key | Default | Effect |
| --- | --- | --- |
| `defaults.subsidiaries` | `[MJP, KOR, USA]` | **The** canonical list. Add a subsidiary here before anywhere else |
| `timeouts.page_load` | `30` | Playwright navigation, seconds |
| `timeouts.element` | `15` | Element waits, seconds |
| `timeouts.api_request` | `30` | httpx request timeout |
| `timeouts.eventual_consistency` | `60` (dev) | Polling budget for lagging stores |
| `features.fe_headless` | `true` | **Set `false` to watch the browser** |
| `features.fe_screenshot_on_failure` | `true` | Attach a screenshot + URL on FE failure |
| `features.fe_trace_on_failure` | `true` | Write a Playwright trace per failed FE case to `reports/traces/<case>.zip`. View with `playwright show-trace <file>` |
| `features.allure_enabled` | `false` | Master switch for all Allure output — run metadata, attachments and the site. Off for now; see "Allure" below |
| `features.auto_generate_allure_report` | `true` | Render the Allure site at the end of each session. Non-fatal when the CLI is absent. Ignored while `allure_enabled` is false |
| `browser.name` | `chromium` | Any Playwright browser |
| `browser.viewport` | `1920x1080` | Applied per browser context |
| `browser.slow_mo_ms` | `0` | Raise to slow the UI down while debugging |
| `environments.dev.next_actions.purchase_checker_login` | `e4e2d05f…` | Next.js server-action id for the login route |

> **`next_actions` is build-coupled.** The id regenerates every time XDB Cross is
> redeployed. If *every* login scenario starts failing at the BE layer at once,
> re-capture it from the browser's network tab before hunting a product bug. Currently
> set for `dev` only — `stg`/`prod` raise a `ConfigError` naming the missing key.

### 4. Module constants — code

| Constant | File | Effect |
| --- | --- | --- |
| `MAX_CONCURRENT_TEST_CASES` | `…/login/orchestrator.py` | Concurrent browser contexts. Default `5`, per `system-flow.md` |
| `SUBMIT_BUTTON` and friends | `…/login/fe.py` | Selectors. `.style_login_btn__0YZb9` is a CSS-module hash — build-coupled like `next_actions` |

### Precedence

For **secrets**, highest first:

1. Real process environment variables (CI secrets, `ENV=stg python -m pytest …`)
2. `.env.<env>`

For the **run target**: `--flag` → matching **process** env var
(`ENV`/`SUBSIDIARY`/`DATA_SET`, which also accept `dev,stg`) → **every configured value**.

Two things worth knowing about that last step:

- The fallback reads the *process* environment only, **not** `.env.<env>`. Those files set
  `ENV` and `DATA_SET` as per-environment config, and honouring `DATA_SET=test` from
  `.env.dev` would mean a bare `pytest` never ran the `real` data set — the opposite of
  the full-coverage default. `ENV=stg python -m pytest …` and CI (which passes the target
  as environment variables) are unaffected.
- Setting one variable narrows only *that* dimension. `ENV=stg python -m pytest …` runs
  stg against every subsidiary and both data sets.

There is no shared base `.env`; each environment's file is self-contained.

## Common invocations

```bash
# BE only — fast, no browser
python -m pytest -m "module and be" lib/app/modules/purchase_checker/login --subsidiary MJP

# Refresh the stored bearer token for a subsidiary
python -m pytest -m module lib/app/modules/purchase_checker/login --subsidiary MJP --data-set real

# All negative scenarios, watching the browser
#   (set features.fe_headless: false in settings.yaml first)
python -m pytest -m module lib/app/modules/purchase_checker/login --subsidiary KOR --data-set test

# Everything that collects
python -m pytest
```

Bypassing pytest entirely — useful when debugging one subsidiary:

```python
import asyncio
from lib.app.modules.purchase_checker.login import orchestrator

results = asyncio.run(orchestrator.run("dev", "MJP", "test"))
for r in results:
    print(r["test_case"], r["errors"] or "PASS")
```

## Viewing results

Three artifacts, in increasing order of detail.

### 1. Console

Live INFO logging is on (`log_cli = true`), so each run streams
`BE: starting …` / `FE: finished …` milestones as they happen.

### 2. HTML report — works with no extra tooling

```
reports/pytest-report.html
```

Self-contained (`--self-contained-html`), regenerated every run, opens in any browser.
This is the practical answer on a machine without the Allure CLI.

```bash
start reports/pytest-report.html      # Windows
open  reports/pytest-report.html      # macOS
```

### 3. Allure — the full report with attachments

> **Currently disabled.** `features.allure_enabled: false` in `settings.yaml`, and
> `--alluredir` is commented out in `pytest.ini`. A run writes **no** files under
> `reports/allure-results/` and generates no site; use the pytest HTML report above
> meanwhile. All the reporting code is intact — modules still call the attachment helpers
> and those simply no-op. To turn it back on, flip the flag **and** un-comment
> `--alluredir` (the flag alone isn't enough — `--alluredir` is what activates
> `allure-pytest` in the first place). The rest of this section describes that enabled
> state.

Raw results are written to `reports/allure-results/` on every run and include:

- `environment.properties` — the run's env / subsidiary / data set
- `purchase_checker/login: summary` — per-scenario pass/fail, the failing stage, and any
  stage that was legitimately skipped
- `purchase_checker/login: full results` — every layer's result. Secrets are projected out
  before attachment: a login shows `token_issued: true`, never the token itself
- On FE failure: a full-page screenshot, the page URL, and a Playwright trace

The HTML site is generated **automatically at the end of every pytest session**, into
`reports/allure-report/`. To view it:

```bash
allure open reports/allure-report     # serves it on a local port
start reports/allure-report/index.html   # or just open the file (Windows)
```

To re-render without re-running the suite:

```bash
allure generate reports/allure-results -o reports/allure-report
```

### Installing the CLI

Already installed here as **Allure 3** (`allure` v3.x, from npm):

```bash
npm install -g allure
```

**Use this route, not the Java one.** There are two different Allure CLIs and only one is
practical on a locked-down Windows machine:

| | Allure 2 (`allure-commandline`) | Allure 3 (`allure`) — what we use |
|---|---|---|
| Runtime | Java 8+ | Node only |
| Install | `scoop`/`choco`/`winget` — needs **admin** | `npm install -g allure`, no admin |
| `generate` flags | `-o` **and** `--clean` | `-o` only; **`--clean` exits 1** |

On this machine the Java route is a dead end: the only JVM on `PATH` is a 2013-era JRE 7
(Allure needs 8+), installing a modern JDK via `winget` requires a UAC prompt, and
downloading a portable JRE directly fails because corporate TLS interception closes the
connection to `api.adoptium.net`. npm reaches its registry fine, so Allure 3 is the
working path.

Because the two CLIs disagree on flags, `report_generator.generate_report` passes only
`-o` and removes the stale output directory in Python — so it works with either.

Turn the automatic step off with `features.auto_generate_allure_report: false` in
`settings.yaml`, or turn Allure off entirely with `features.allure_enabled: false` (the
current setting). If the CLI is ever missing, the run still passes and logs one WARNING
naming the manual command — a reporting tool never turns a green suite red.

> **Clean between runs.** `reports/allure-results/` **accumulates** — each run appends
> its own result files, so a generated report mixes every run since the last clean, and
> `environment.properties` reflects only the most recent one. Delete the directory
> before a run you intend to publish:
>
> ```bash
> rm -rf reports/allure-results/* && python -m pytest …
> ```

### 4. Logs

```
logs/run_<envs>_<subsidiaries>_<data_sets>.log
```

One file per run, not per combination — a matrix run lists each dimension's values in the
name (`run_dev_MJP+KOR+USA_real+test.log`) and every combination writes into it, tagged by
the `Run target: env=… subsidiary=… data_set=…` line logged as each one starts. Narrow the
run with the flags and the name narrows with it (`run_dev_MJP_test.log`).

DEBUG level — raw request payloads and full response detail, which the console (INFO)
omits. Passwords are masked at the call site and `logging_config._RedactFilter` catches
`password` / `token` / `secret` / `authorization` / `api_key` / `access_key` as a
backstop.

> Because that filter matches on the log *format string* and clears the record's
> arguments when it fires, avoid putting those substrings in a log message's literal
> text — the other interpolated values in that line will be blanked out with it.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `ConfigError: Unknown ENV '...'` | `--env` must be exactly `dev`, `stg` or `prod` |
| `ConfigError: Missing secrets file for ENV` | That `.env.<env>` doesn't exist yet — see `getting-started.md` step 3 |
| `ConfigError: Unknown SUBSIDIARY 'X'. Configured subsidiaries: MJP, KOR, USA` | Not in `settings.yaml`'s `defaults.subsidiaries`. Note `Makefile` and `ci.yml` still default to a stale `subsidiary_001`, which is rejected |
| `ConfigError: Test data directory does not exist` | No `test_data/<module>/<env>/<sub>/<data_set>/` folder for a combination you named **explicitly**. Author it, or drop the flag and let that combination be skipped instead |
| `ERROR: Unknown --env value(s): qa. Configured: dev, stg, prod` | Typo in `--env`/`--subsidiary`/`--data-set`. Validated up front, so nothing ran |
| Lots of `SKIPPED [1] … no test data authored for …` | Expected. An omitted flag expands to every value, and combinations without authored test data are skipped rather than failed. Pass the flags to narrow the run |
| `ConfigError: MONGO_TLS_CA_FILE='certs/mongo-ca-bundle.pem' does not exist` on `--env stg`/`prod` | Config is validated eagerly, so a missing cert blocks the run even for a module that touches no datastore. `.env.stg`/`.env.prod` name `mongo-ca-bundle.pem` and `aws-bastion-key-<env>.pem`, but `certs/` currently holds `global-bundle.pem` and `misumi-ca.pem`. Either add the named files (`getting-started.md` step 4) or blank those two keys for that environment |
| `ConfigError: Unknown next-action` | `settings.yaml` has no server-action id for that environment. Only `dev` is populated |
| Every login scenario fails at the BE layer | The `next-action` id or the FE submit-button class went stale after a redeploy — re-capture both |
| `Login failed: … no GACCESSTOKENKEY cookie` for **USA** | `.env.dev` still holds placeholder `dummy_user_usa` credentials. Fill in the real ones |
| `SELF_SIGNED_CERT_IN_CHAIN` installing browsers | Corporate TLS interception. Use `NODE_EXTRA_CA_CERTS="$(pwd)/certs/misumi-ca.pem" python -m playwright install chromium` |
| `make: command not found` | Not installed here — run the `python -m pytest` command directly |
| `Allure report not generated: The 'allure' commandline is not on PATH` | Install it with `npm install -g allure`. The run still passes meanwhile |
| `allure generate` exits 1 with a usage dump | You're passing Allure 2 flags to Allure 3 — `--clean` no longer exists. Use `-o` alone |
| `Could not create the Java Virtual Machine` from `java` | Irrelevant to Allure 3, which needs no Java. The `java` on `PATH` here is a 2013 JRE 7 |
| A run fails with `No test-data case files for …` | Deliberate: a run that resolves zero cases fails rather than passing green. Check the `<env>/<subsidiary>/<data_set>/` folder actually contains case files |
| 13 errors from a bare `python -m pytest` | Expected: `etl/gdb`, `e2e` and `critical_path` are still placeholders |
