# Plan: purchase_checker/login

Filled in during Steps 1–3 of the `new-module-scaffold` skill, **before any code or
test-data file is generated**. This is the single source of truth for what this module
does, what it tests, and how — code/test-data generation in later steps reads from
this file, and it's updated first if any of these decisions change later.

Status: confirmed

## 1. Module identity

- Domain: `purchase_checker`
- Module name: `login`
- Path: `lib/app/modules/purchase_checker/login/`
- Purchase Checker flow node(s): `S1` — the single entry gate; the one confirmed
  S-identifier→module mapping in `docs/context/module-workflows.md`.
- Depends on another module's state?: `none`. This module is the dependency — every
  other `purchase_checker` module calls **this module's `be.py` only**, via
  `await login_be.login(env, subsidiary_cd, credentials)`. That signature is a
  cross-module contract, not a local detail; changing it breaks callers.

## 2. Layers in use

- [x] BE (`be.py`) — endpoint: `POST {credentials.fe_url}/login/`, a **Next.js server
      action**, not a REST endpoint. Requires the `next-action` header carrying the
      build-generated action id (`Config.next_action("purchase_checker_login")`), and a
      `multipart/form-data` body with fields `1_loginId`, `1_password`, `1_country`, and
      `0` = `[null,"$K1"]`. Auth is returned as the `GACCESSTOKENKEY` cookie in a
      `Set-Cookie` response header.
- [x] FE (`fe.py`) — the XDB Cross customer-facing app (**not** the Admin Panel, which is
      what this template's wording assumes). Entry `credentials.fe_url`, then the
      locale login link. Selectors: `a[href="/{locale}/login"]`, `#loginId`, `#password`,
      `.style_login_btn__0YZb9`, and an `h1` reading `Purchase Checker` as the success
      signal.
- [ ] DB — which stores: **none**.
  - [ ] `postgres_gdb`
  - [ ] `postgres_repl`
  - [ ] `mongo`
  - [ ] `opensearch`
  - [ ] `s3`

  `module-workflows.md`'s Known gaps says the `purchase_checker` data-layer wiring is
  unconfirmed in the source flow doc — *"Don't assume a `db/*_checks.py` target for a
  `purchase_checker` module until that wiring is confirmed."* No `db/` directory is
  created; an absent file is the signal, per `system-flow.md`.

An unchecked layer gets no file for this module — an absent file is the correct
signal (see `docs/context/system-flow.md`), not a stub raising `NotImplementedError`.

## 3. Environments & subsidiaries

- Environments: `dev` only. A deliberate narrowing of the skill's `dev/stg/prod` default
  — `settings.yaml` only carries the login server-action id for `dev`, and that id is
  build-specific, so `stg`/`prod` need their own captured value before they can run.
- Subsidiaries: `MJP`, `KOR`, `USA` (all three).

`1_country` is derived as `subsidiary_cd.lower()` → `mjp`/`kor`/`usa`. The locale
(`ja`/`ko`/`en_US`) is derived from `FE_URL_<SUB>` via `url_helper.locale_of`, so there
is no second subsidiary→locale map to drift.

> Note: `xdb_cross_system_flow.md` §1 records the login input as `JPN / KOR / USA` and
> the output as a session carrying `sub` / `subsidiary_code` / `language_code`. Both are
> contradicted by the live contract — the wire value is `mjp`, and the response is an
> opaque cookie, not a decodable session object. Recorded in that doc's Known gaps.

## 4. Expected-value source

(See `docs/context/test-data-conventions.md`, "Where the 'expected result' comes from".)

- [x] Live `be_result` (default — use this whenever `be.py` produces the state under test)
- [x] Test-data-defined — hardcoded literally in the test-data file
- [ ] Test-data-defined — resolved from the DB/backend at run time by this module's own code

Both, and the split is deliberate rather than indecision:

- **Live `be_result` wherever one exists.** `fe.py` asserts the browser's session cookie
  has the same *name*, `domain` and `path` the BE's `Set-Cookie` declared. The cookie
  *value* legitimately differs — the browser authenticates in its own session — so
  comparing values would be wrong, not stricter.
- **Test-data-defined only for what no BE result can supply**: the FE error message text
  for a rejected login. It's rendered by the frontend, locale-specific, and never appears
  in the BE response, so it lives in the per-subsidiary test-data file.

## 5. Test data schema

Fields every test-data file for this module contains, confirmed with the user before
any file is generated:

| Field | Type | Meaning |
| --- | --- | --- |
| `name` | string | scenario name — should match the file name |
| `description` | string | what this case exercises, for the report |
| `login_id` | string \| null | login id override. `null` → use `FE_USERNAME_<SUB>` from `.env.<env>` |
| `password` | string \| null | password override. `null` → use `FE_PASSWORD_<SUB>` from `.env.<env>` |
| `country` | string \| null | `1_country` override for the BE, and the subsidiary whose locale login page the FE drives. `null` → `subsidiary_cd.lower()`, i.e. this run's own pages |
| `fe_applicable` | bool | Optional, defaults `true`. `false` marks a scenario that cannot be expressed through the UI, so the FE layer records a skip instead of running. See the note below |
| `expect_success` | bool | drives `be.login` vs `be.login_expect_failure`, and whether FE expects the heading or the error |
| `expected.error_message` | string \| null | FE error text for a rejected login. Locale-specific, hence authored per subsidiary. `null` → the FE asserts only that no session cookie was issued |

**On `country` and the two layers' routes to it.** The browser cannot set `1_country`: it
submits the country belonging to the locale page it is on (`/ja/` → `mjp`). That is a
difference in *route*, not in coverage, so the FE expresses the same scenario by driving
the overridden country's locale login page (`/ko/login`) with this run's credentials —
`fe.config_for_country` resolves that page from `FE_URL_<SUB>`, reusing the existing
country↔subsidiary mapping rather than adding one. This is also the only version of the
scenario a real user can reach, so a leak found here is the stronger finding.

Credentials always come from the run's own subsidiary; only the pages change. Any error
text on such a page renders in the *other* locale's language, which is why
`expected.error_message` is `null` for this case and the FE asserts the cookie instead.

**On `fe_applicable`:** an escape hatch for a scenario with no UI form at all. **No current
scenario uses it** — `S1_mismatched_country` did until the FE route above was implemented.
It is kept in the schema and honoured by the orchestrator for future BE-only scenarios; an
earlier version of this plan cited the country override as its example, which is no longer
accurate.

**No real credentials in test data** (`test_data/README.md`: *"Usernames/passwords/tokens
live in `.env.<env>` and CI secrets"*). Valid credentials are always `null` here and come
from the environment; only synthetic invalid values appear as literals.

## 6. Scenarios

One row = one planned test-data file, at
`test_data/purchase_checker/login/<env>/<subsidiary>/{real,test}/<file>`. File naming
follows `docs/context/test-data-conventions.md` — a ticket ID or descriptive scenario
tag, never `test1.json`; `module-workflows.md` additionally requires the scenario-workbook
identifier, hence the `S1_` prefix. `real/` vs `test/` per file follows the same doc's
data-character split (production-like vs. synthetic edge case), not this table's category.

### Happy path

| File | Description | Expected outcome |
| --- | --- | --- |
| `real/S1_valid_login.json` | Real subsidiary credentials from `.env.<env>`, country matching the subsidiary | 200-class response with `GACCESSTOKENKEY` in `Set-Cookie`; `Bearer <token>` persisted to `BE_API_TOKEN_<SUB>`; FE shows the `Purchase Checker` `h1` |

### Error cases

| File | Description | Expected outcome |
| --- | --- | --- |
| `test/S1_invalid_password.json` | Valid login id from env, deliberately wrong password | Rejected, no `GACCESSTOKENKEY` issued; FE stays on the login page and shows the error |
| `test/S1_unknown_user.json` | Login id that does not exist in the subsidiary | Rejected, no cookie; FE shows the error |
| `test/S1_empty_credentials.json` | Both fields submitted empty | Rejected; FE surfaces validation without reaching the Purchase Checker page |

### Edge cases

| File | Description | Expected outcome |
| --- | --- | --- |
| `test/S1_mismatched_country.json` | Valid credentials for this subsidiary, `1_country` set to a different one (MJP→kor, KOR→usa, USA→mjp). BE posts the overridden field; FE signs in on that country's locale login page | Rejected by both layers — credentials must not authenticate across subsidiary scopes. A pass here would be a cross-tenant leak |
| `test/S1_overlong_login_id.json` | 303-character login id | Rejected cleanly — not a 5xx, and not a truncated match |
| `test/S1_sql_injection_login_id.json` | `' OR '1'='1` in both fields | Rejected, never authenticated. Security regression guard |

> A scenario varying only the *whitespace padding* of a valid login id was considered and
> dropped: it needs the real login id as a literal in the test-data file, which
> `test_data/README.md` forbids. It would need a "transform the env value" field to be
> expressible, which isn't worth adding for one case.

## 7. Status checklist

- [x] Plan confirmed with the user (Step 3)
- [x] Code generated: orchestrator/be/fe (Step 4) — no `db/`, per Section 2
- [x] Test-data files generated for `dev` × MJP/KOR/USA, matching Section 6 (Step 5)
- [x] Negative-scenario content authored — the six `test/` cases carry real synthetic
      values, not placeholders. The happy-path case is intentionally all-nulls: its
      credentials live in `.env.<env>` and must not be copied into test data.
- [ ] `expected.error_message` outstanding for every rejecting scenario (3 locales × 6
      cases). Left `null` rather than guessed — the module asserts only "login was
      rejected" until the real strings are captured from the app, so an invented string
      can't produce a false failure.

## 8. Operational notes

- **Only the `real/` data set mints a token.** `Config.test_data_dir` selects
  `real/` or `test/` from `DATA_SET`, and the happy path is the only `real/` case. A
  default run (`DATA_SET=test` in `.env.dev`) exercises the six rejection scenarios and
  deliberately writes nothing to `BE_API_TOKEN_<SUB>`. Run with `--data-set real` to
  refresh the stored token.
- **`next_actions.purchase_checker_login` in `settings.yaml` is build-coupled.** If every
  scenario starts failing at the BE layer at once, re-capture the action id from the
  browser's network tab before looking for a product bug. The FE's
  `.style_login_btn__0YZb9` selector has the same property.
- **A rejected login is proven by the absence of a `GACCESSTOKENKEY` cookie**, not by the
  absence of the success heading. An earlier version asserted only the latter and was
  demonstrated to report "correctly rejected" after a login that had actually succeeded.
  Keep the cookie assertion as the primary signal if this file is ever revised.
- **The token never reaches a report.** `LoginResult.to_report_dict()` is the only thing
  that may be attached; attaching the dataclass itself publishes the bearer token via its
  `__repr__`.
