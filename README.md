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

```bash
make test-critical                  # smoke
make test-e2e                       # full cross-module
make test-module M=etl/gdb          # one module
make cli ARGS="--suite e2e"         # via the CLI entrypoint
pytest -m "db and postgres"         # by marker
pytest -n auto                      # parallel
```

Reports:

```bash
make report-open    # allure generate + open
```

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
