# Module Workflows

Confirmed: modules live under exactly two domains in `lib/app/modules/` —
**`etl`** and **`purchase_checker`**. `etl/gdb` and `purchase_checker/login` (referenced
elsewhere in the docs) are existing modules within these domains, not just illustrative names.

**The per-domain workflow detail below is still a placeholder — to be added later.** Read this
file before assuming how a domain's flow works; if the section for a domain is still a TODO,
ask rather than inferring it from a single existing module.

## `etl`

**Still TODO — not yet provided.** Do not infer this domain's workflow from `purchase_checker`
below; the two are unrelated systems. Will cover: what triggers an `etl` module's flow, which
be/fe/db layers `etl` modules typically use, how their test cases are shaped, and any
conventions specific to pipeline/data-flow validation.

## `purchase_checker`

System under test: **XDB Cross** (`stg01.cross-dev.misumi-ec.com`). Full call-by-call detail
lives in `docs/context/purchase_checker/xdb_cross_system_flow.md` — read it before touching any
`purchase_checker` module; the summary below is orientation only, not a substitute.

**What the system does:** a user submits part numbers (competitor or MISUMI), the system
classifies each one against the catalog, finds MISUMI replacement parts, and lets the user
compare specs before downloading CAD data or ordering.

**Session precondition:** every `purchase_checker` module sits downstream of **Login (S1)**,
which produces `sub`, `subsidiary_code`, `language_code` — reused by every module in the
session. This is the concrete case of `system-flow.md`'s cross-module dependency pattern: a
`purchase_checker` module other than login should import and call **only** `login`'s `be.py`
to establish session state, never login's `fe.py`/`db/*`/`orchestrator.py`.

**Shape of the flow** (see the linked file for the full module list, request/response fields,
and the four-case classification table):

1. **Entry** — three mutually exclusive paths into classification: typed search, BOM Excel
   upload, or history-restore (which skips classification entirely).
2. **Classification** (`part-number` API) — runs once per row, returns one of four cases
   (Match / Not unique / Fuzzy match / No match) that determines the rest of that row's path.
3. **Branch resolution** — Not unique and Fuzzy match route through a shared correction
   module; No match routes through an edit modal that re-submits into classification. No case
   is a dead end.
4. **Result page** — persistence (`bom-log`, `save-user`) runs in parallel with the
   replacement search (`default-replacement` + external EC type search).
5. **Spec comparison / narrowing loop** — the only rendering surface for replacement data;
   toggling specs re-runs a `custom-replacement` search and re-renders, looping as needed.
6. **Exit** — download (gated behind a terms-of-use consent check) or add-to-cart (hands off
   to the separate MISUMI EC site with its own login).

**Data layer:** Postgres, MongoDB, S3, OpenSearch/GDB, plus two ETL processes (XDB and GDB)
back classification and replacement search — but the linked file is explicit that **the wiring
between these components and individual modules is unconfirmed** (particularly MongoDB's role
and how the two ETL processes feed Postgres/OpenSearch). Don't assume a `db/*_checks.py` target
for a `purchase_checker` module until that wiring is confirmed for the specific module — ask
rather than guessing which store to check.

**Test data naming:** the source doc retains module identifiers (`S1`–`S25`, `N1`–`N4`) from
the scenario workbook. Include the relevant identifier alongside the ticket ID when naming
`purchase_checker` test-data files (per `test-data-conventions.md`'s naming convention) so a
failure traces back to both the ticket and the scenario-workbook step, e.g.
`NDFDPAPJ-XXXX_S6_default_replacement_no_brand_code.json`.

## Known gaps

Tracked here so nothing gets lost. Don't guess past these — ask or wait for the missing piece.

- **`etl` domain workflow — not yet provided.** The whole `## etl` section above is a stub.
- **XDB Cross → repo module mapping — not yet defined.** `xdb_cross_system_flow.md` describes
  the *application's* flow using its own scenario-workbook identifiers (`S1`–`S25`, `N1`–`N4`);
  it does not say how those map onto `lib/app/modules/purchase_checker/<module_name>/` folders.
  `login` (S1) is the one confirmed mapping so far, by name match. Which of the remaining
  identifiers become their own module vs. get grouped into one (e.g. does classification's
  four-case branch resolution live in one module or several?) needs to be decided — via
  `new-module-scaffold`'s Step 1 — before scaffolding any of them, not inferred from the flow
  doc's grouping.
- **XDB Cross data-layer wiring — unconfirmed in the source doc itself.** Which of Postgres,
  MongoDB, S3, OpenSearch/GDB actually backs which module's `db/*_checks.py` is unresolved,
  specifically MongoDB's role and how the two ETL processes (XDB, GDB) feed Postgres/OpenSearch.
  Consequence so far: **`purchase_checker/login` ships as BE+FE only** — it has no `db/`
  directory, and `lib/app/e2e/orchestrator.py` / `lib/app/critical_path/orchestrator.py` had
  their `login.db.*` imports removed accordingly. Restore them together with the directory
  once the wiring is confirmed.
- **`xdb_cross_system_flow.md` §1 is contradicted by the live login contract.** Two specifics,
  found while building `purchase_checker/login` against `stg01.cross-dev.misumi-ec.com`:
  - It records the subsidiary input as `JPN / KOR / USA`. The wire value is actually the
    lowercased repo subsidiary code — `mjp` / `kor` / `usa` — sent as the `1_country` form
    field. There is no `JPN`.
  - It records the output as "a session containing `sub` (user_code), `subsidiary_code`,
    `language_code`". What the app actually returns is an **opaque `GACCESSTOKENKEY` cookie**
    in a `Set-Cookie` header — not a decodable session object. Those three fields cannot be
    read from it, so `LoginResult` does not carry them. Any downstream module's design that
    assumed it could read `sub`/`subsidiary_code`/`language_code` from the login result needs
    revisiting.

  Login is also a **Next.js server action**, not a REST endpoint: it is selected by a
  build-generated `next-action` header id, which lives in `settings.yaml` per environment and
  regenerates on every deploy of the app under test.
- **BOM upload route — unconfirmed whether `save-user` call site 1 fires.** Affects whether an
  `excel-upload`-based module needs to assert a dataset-reservation call at all.
- **`xdb_cross_system_flow.md` numbering skips section 10** (goes `## 9` → `## 11`) in the
  source as provided — flagged here rather than silently renumbered, in case content is
  missing rather than the numbering being intentional.

## Adding a third domain

Don't add one without updating this file and `CLAUDE.md`'s "Domains" section first — the two
domains above are treated as an exhaustive list elsewhere in the docs (e.g.
`folder-structure.md`'s tree) until this changes.
