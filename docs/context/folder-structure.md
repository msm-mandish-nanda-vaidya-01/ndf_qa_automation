# Folder Structure

Where things live, and why. If you're not sure where a new file belongs, check here before
guessing — and if genuinely nothing fits, ask rather than inventing a new top-level convention.

```
ndf_qa_automation/
├── .env                          # actual secrets (gitignored, never committed)
├── .env.example                  # template with dummy values, committed
├── .gitignore
├── .pre-commit-config.yaml       # black/ruff/isort hooks
├── pyproject.toml                # black/ruff/isort config, project metadata
├── pytest.ini
├── requirements.txt
├── README.md
├── Makefile                      # make test-module / test-e2e / lint
│
├── CLAUDE.md                     # entry point Claude reads first — rules + reference index
├── docs/context/                  # detail docs CLAUDE.md links out to, read before related work
│   ├── system-flow.md             # orchestrator/be/fe/db wiring, concurrency, error handling
│   ├── test-data-conventions.md   # test_data path convention + where expected values come from
│   ├── folder-structure.md        # this file
│   ├── module-workflows.md        # etl vs purchase_checker domain workflows + known gaps
│   └── purchase_checker/
│       └── xdb_cross_system_flow.md   # full flow of the system purchase_checker tests
│
├── .github/workflows/ci.yml      # lint + smoke/critical-path run on PR (non-interactive CLI)
├── .claude/skills/                # project-local skills (e.g. new-module-scaffold)
│
├── lib/
│   ├── core/                      # shared infrastructure — never module-specific logic here
│   │   ├── utils/
│   │   │   ├── url_helper.py         # build env/subsidiary-aware URLs
│   │   │   ├── report_generator.py   # formats results + attaches to Allure
│   │   │   ├── wait_helper.py        # retry/backoff for BE calls + eventually-consistent DB checks
│   │   │   └── data_loader.py        # resolves test_data/<module>/<env>/<subsidiary>/<real|test>/
│   │   ├── db/
│   │   │   ├── postgres_client.py    # pooled connection, shared across all modules
│   │   │   ├── mongo_client.py       # pooled connection, shared across all modules
│   │   │   └── opensearch_client.py  # pooled connection, shared across all modules
│   │   ├── aws/s3_client.py
│   │   ├── fixtures/                 # pytest fixtures (conftest.py, fe/be/db fixtures)
│   │   └── config/
│   │       ├── env_config.py         # reads secrets from os.environ (via .env + python-dotenv)
│   │       ├── settings.yaml         # non-secret: URLs, timeouts, env/subsidiary lists, flags
│   │       └── logging_config.py     # sets up console + per-run file handler
│   │
│   └── app/
│       ├── main/main.py           # CLI entry point (questionary interactive menu + argparse for CI)
│       │
│       ├── modules/                # two domains, each its own workflow — see module-workflows.md
│       │   ├── etl/                  # pipeline/data-flow modules
│       │   │   └── gdb/
│       │   │       ├── orchestrator.py   # be -> fe -> db/* for this module
│       │   │       ├── be.py
│       │   │       ├── fe.py
│       │   │       └── db/{postgres,mongo,opensearch,s3}_checks.py
│       │   └── purchase_checker/     # user-facing search/cross-reference/order flow modules
│       │       └── login/
│       │           └── (same shape)
│       │
│       ├── e2e/orchestrator.py         # imports be/fe/db across multiple modules, full journeys
│       └── critical_path/orchestrator.py  # imports a smoke-level subset, still checks persisted state where critical
│
├── test_data/                     # see test-data-conventions.md for the full path/schema convention
│   └── <module_path>/<env>/<subsidiary_cd>/{real,test}/
│
├── logs/                          # gitignored — one .txt per run, console mirrors it
│
└── reports/
     ├── allure-results/           # gitignored — raw allure-pytest output per run
     ├── allure-report/            # gitignored — generated static HTML site
     └── (pytest-html / json-report output, if kept)
```

## Rules of thumb

- **New shared logic** (used by 2+ modules) → `lib/core/utils/` or `lib/core/db/`, never
  duplicated inside a module. Check there first.
- **New module** → `lib/app/modules/<domain>/<module>/`, scaffolded via the
  `new-module-scaffold` skill so the orchestrator/be/fe/db shape and docstrings stay consistent.
- **New test data** → under `test_data/`, following `test-data-conventions.md` exactly — don't
  invent a different nesting order (e.g. subsidiary before env).
- **Cross-module e2e/critical-path logic** → `lib/app/e2e/` or `lib/app/critical_path/`, which
  import from `modules/*` — module code itself never imports from `e2e/` or `critical_path/`.
