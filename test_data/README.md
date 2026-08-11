# Test data

```
test_data/<area>/<feature>/<env>/<subsidiary>/<data_set>/<case>.json
```

Resolved at runtime by `get_config().test_data_dir("etl/gdb")` from `ENV`,
`SUBSIDIARY` and `DATA_SET`, and loaded via
`lib.core.utils.data_loader.load_case(...)`.

- `real/` — snapshots or references to production-like records. Read-only.
- `test/` — synthetic fixtures safe to create, mutate and re-run.

Rules:

- **No credentials.** Usernames/passwords/tokens live in `.env.<env>` and CI secrets.
- Keep `expected` blocks minimal. Anything the BE returns is read from the BE
  result object at runtime, not restated here — otherwise the FE/DB layers stop
  validating against the BE and start validating against a hardcoded guess.
- Mirror a new case into every `<env>/<subsidiary>/<data_set>/` combination the
  suite runs against, or the run fails on a missing file.

Currently seeded with `happy_path.json` placeholders under
`dev/subsidiary_001/test/` only. The remaining combinations hold `.gitkeep` and
need real cases filled in.
