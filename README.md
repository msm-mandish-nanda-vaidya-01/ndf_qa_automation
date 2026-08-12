# NDF QA Automation

Layered QA automation. Every module follows the same three-step contract:

```
be.py      performs the action              -> returns response / state
fe.py      takes the BE result as input     -> asserts the UI matches it
db/*.py    verify persisted state           -> postgres, mongo, opensearch, s3
```

`orchestrator.py` in each module sequences those three steps. Nothing above the
module layer re-implements them — `e2e/` and `critical_path/` import the same
`be`/`fe`/`db` units and only decide *which* ones run and in what order.

## Layout

| Path | Purpose |
| --- | --- |
| `lib/core/` | reusable machinery: clients, fixtures, config, utils — no test logic |
| `lib/app/modules/<area>/<feature>/` | one feature flow: `orchestrator` + `be` + `fe` + `db/` |
| `lib/app/e2e/` | cross-module end-to-end sequences |
| `lib/app/critical_path/` | smoke subset; still verifies persisted state where critical |
| `lib/app/main/main.py` | argparse CLI entrypoint |
| `test_data/<area>/<feature>/<env>/<subsidiary>/{real,test}/` | fixtures per env + subsidiary |
| `reports/` | allure results + generated site (gitignored) |
| `logs/` | runtime logs (gitignored) |

## Setup

First time pulling this repo? Follow **[docs/setup/getting-started.md](docs/setup/getting-started.md)**
— it covers creating `.env.dev`/`.env.stg`/`.env.prod`, per-subsidiary credentials, and
the two `.pem` files (`certs/`) MongoDB/DocumentDB needs. Short version once you've done
that once:

```bash
python -m venv .venv && source .venv/Scripts/activate   # Windows bash
make install
make install-hooks
```

`.env.dev` / `.env.stg` / `.env.prod` hold **secrets only** and are never committed;
`env_config.py` picks the file matching `ENV`. Non-secret config — URLs, timeouts,
feature flags — goes in `lib/core/config/settings.yaml`, keyed by environment.

## Running

Full command reference, every modifiable parameter, and how to read the results:
**[docs/setup/running-tests.md](docs/setup/running-tests.md)**.

Short version — `purchase_checker/login` is the only module implemented end to end
today, and `pytest` is the interface (`lib/app/main/main.py` still raises
`NotImplementedError`, and the `Makefile` targets below assume a `make` that isn't
installed on every dev machine):

```bash
# one module, explicit run target
python -m pytest -m module lib/app/modules/purchase_checker/login \
    --env dev --subsidiary MJP --data-set test

python -m pytest -m "module and be" …    # by marker
python -m pytest                          # everything that collects
```

`--data-set` picks which scenarios run: `test` = negative cases, `real` = the happy
path (which also refreshes `BE_API_TOKEN_<SUB>` in `.env.<env>`).

Reports — `reports/pytest-report.html` (self-contained) is written every run.

**Allure is switched off for now** (`features.allure_enabled: false` in `settings.yaml`,
`--alluredir` commented out in `pytest.ini`), so no `reports/allure-results/` files and no
Allure site are produced. The reporting code is untouched and still called; it no-ops
while the flag is false. Re-enable by flipping the flag *and* restoring `--alluredir` —
see [docs/setup/running-tests.md](docs/setup/running-tests.md#3-allure--the-full-report-with-attachments).

## Adding a module

1. `mkdir -p lib/app/modules/<area>/<feature>/db` and add `__init__.py` files.
2. Copy the four-file contract: `orchestrator.py`, `be.py`, `fe.py`, `db/*_checks.py`.
3. Add test data under `test_data/<area>/<feature>/<env>/<subsidiary>/{real,test}/`.
4. Register the module in `lib/app/main/main.py` and, if it belongs there,
   in `e2e/orchestrator.py` / `critical_path/orchestrator.py`.

## Conventions

- `fe.py` never re-derives expected values — it receives them from `be.py`.
- DB checks assert on persisted state, not on the BE response echo.
- Markers: `module`, `e2e`, `critical_path`, `be`, `fe`, `db`, plus one per store.
- Test data selection is driven by `ENV`, `SUBSIDIARY`, and `DATA_SET`.
