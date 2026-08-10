# XDB Cross — System Flow Reference

Environment: `stg01.cross-dev.misumi-ec.com`

Purpose of the system: a user submits part numbers (competitor or MISUMI), the
system classifies each one against the catalog, finds MISUMI replacement parts,
and lets the user compare specifications before downloading CAD data or ordering.

Module identifiers (`S1`–`S25`, `N1`–`N4`) are retained because they are the
identifiers used in the scenario workbook and the source diagram.

---

## 1. Session context

**Login (S1)** is the single entry gate.

- Input: subsidiary selection (JPN / KOR / USA), loginID, password
- Output: session containing `sub` (user_code), `subsidiary_code`, `language_code`

Every module downstream reuses those three session fields. Subsidiary selection
determines catalog scope, language, and pricing context for the whole session.

---

## 2. Entry paths (home page)

Three mutually exclusive routes lead into the system. Two lead to classification;
one bypasses it.

### 2a. Typed route

1. User types part numbers into the search box.
2. **save-user, call site 1 (S4)** — `POST /dev/new-search/save-user`
   - Input: `sub`, `dataset_id`, `dataset_name`, `memo`, `data: [null]`,
     `subsidiary_code`, `language_code`
   - Output: `dataset_id`
   - The dataset is reserved **before** any search runs. `data` is `[null]` at
     this point; row content arrives at call site 2.
3. Proceeds to classification.

### 2b. BOM upload route

1. **excel-upload (S23)** — accepts a BOM `.xlsx` containing part number,
   quantity, unit price, delivery date. No file-level validation is performed.
2. **BOM column mapping (N1)** — front-end only. Maps parsed rows to
   `part_number`, `quantity`, `unit_price`, `delivery_date` per row.
3. Proceeds to classification.
   *Unconfirmed: whether save-user call site 1 also fires on this route.*

### 2c. Restore route (bypasses classification)

1. **user-history (S22)** — `POST /dev/new-search/user-history`
   - Input: `sub`, `load_index`, `subsidiary_code`, `language_code`
   - Output: `count`, `data[]` — `user_code`, `dataset_id`, `dataset_name`,
     `memo`, `search_source`, `saving_datetime`, `count_before_part_numbers`
   - Paged by `load_index`. Written by save-user.
   - Called at two sites: from the home page, and again from the history page.
2. **history-list page (N3)** — `GET /[country]/history-list?_rsc=…`, a Next.js
   RSC page route returning page markup only, no dataset rows.
3. **user-restore (S21)** — input `dataset_id`, output saved before/after
   replacement rows. Skips classification and lands directly on the result page.

### Home-page leaves (no downstream effect)

- **announcement-list (S25)** — `GET /dev/announcement-list`; input `env`,
  `subsidiary_code`, `language_code`; output `announcements[]`
- **brand-list (S24)** — `GET /dev/brand-list`; input `env`, `language_code`
  (no `subsidiary_code`); output `parentCategoryList[] → categoryList[] →
  brandList[]`, `imageName`

---

## 3. Classification

**part-number API (S2)** — `POST /dev/new-search/part-number`

- Runs **once per row**.
- Input: `sub`, `data[]` (`part_number`, `quantity`, `unit_price`,
  `delivery_date`), `subsidiary_code`, `language_code`
- Output:
  - `before_replacement_part_numbers[]` — `part_number`, `part_number_local`,
    `part_number_type`, `brand_name`, `brand_code`, `category`, `quantity`,
    `unit_price`, `delivery_date`
  - `correct_list[]` — `part_number`, `brand_name`, `brand_code`, `category`,
    `params`, `equations`, `part_number_to_params_mapping`
  - `exist_part_number_at_service`, `is_part_number_unique`

The two booleans plus whether `correct_list` is populated select exactly one of
four cases per row:

| Case | `exist` | `unique` | `correct_list` | Meaning |
|---|---|---|---|---|
| Match (S3a) | true | true | — | Clean hit. Output is a replacement count badge (0 when the part has no replacements). |
| Not unique (S3d) | true | false | — | One part number sold under several brands. |
| Fuzzy match (S3c) | false | false | populated | No exact hit; candidate part numbers offered. |
| No match (S3b) | false | false | empty | Nothing found; all identity fields empty. |

Match passes straight to the result page. The other three require resolution.

---

## 4. Branch resolution (feedback loop)

No branch is a dead end. Every unresolved case has a path back into
classification or forward to the result page.

### Fuzzy match and Not unique → correction module (S8)

One module, two input shapes, one output contract.

- Input: `correct_list[]` (from Fuzzy match) **or** the competing brand set
  (from Not unique)
- Output: `corrected_part_number`, `corrected_part_number_type`,
  `corrected_part_number_local`, `corrected_brand_name`, `corrected_category`

### No match → edit modal (N4)

- Input: the unmatched part number
- Output: edited `part_number`; sets `has_edited`; retains
  `original_part_number`
- The edited part number is sent back through classification, so all four cases
  are in play again. A single row may cycle through classification more than
  once.

Consequence: a row arriving at the result page may carry `corrected_*` values
and `has_edited` that were absent from the original input.

---

## 5. Result page (`/[country]/result/`)

Two things happen in parallel: persistence, and the replacement search.

### 5a. Persistence

**bom-log, call site 1 (S5)**

- Input: `bom_name`, `user`, `country`, `dataset_id`, `created_date`, `save_date`,
  and `entries[]` — `search_pn{pn, brand, category, qty, unit_price, ship_date}`,
  `search_results`, `correct_pn{}`, `crossed_pn{}`, `candidate_matches[]`
- Output: `statusCode 200`, body `message`
- `search_results` carries the case symbol per row.

**save-user, call site 2 (S4)** — after the search

- Input: `sub`, `dataset_id`, `dataset_name`, `memo`, `subsidiary_code`,
  `language_code`, and `data[].before_replacement_part_numbers` —
  `part_number`, `part_number_type`, `part_number_local`, `brand_name`,
  `category`, the five `corrected_*` fields, `quantity`, `unit_price`,
  `delivery_date`, `exist_part_number_at_service`, `is_part_number_unique`,
  `original_part_number`, `has_edited`
- `data[].after_replacement_part_numbers` is **null** at this point.
- Output: `dataset_id`
- Carries `corrected_*` from the correction module and `has_edited` from the
  edit modal.

### 5b. Replacement search

**default-replacement (S6)** — `POST /dev/new-search/default-replacements`

- Input: `brand_name`, `part_number`, `part_number_type`, `part_number_local`,
  `category`, `subsidiary_code`, `language_code`
  (payload carries no `brand_code`, only `brand_name`)
- Output: `main_data` (`brand_code`, `environ_value_list`, `params_list`,
  `series_name`), `notes_list[]` (`diff`, `value`, `unit`, `match`),
  `basic_spec_list[]` (`name`, `value`, `unit`), `replace_list[]` (with
  `match_flag`)

**EC type search (S7)** — `GET api/v1/type/search`, external, leaf, called per
candidate

- Input: `partNumber`, `brandCode`, `lang`, `applicationId`, `sessionId`
- Output: EC master data, unit price, delivery date

---

## 6. Spec comparison and refinement

**spec list (S9)** is the **only rendering surface** for replacement data —
both the default set and the custom set render through it.

- Input: `main_data` + `replace_list[]`, from either the default replacement set
  or the custom replacement set
- Output: comparison table plus row selection consumed by the download and cart
  actions

**red highlight (S10)** — leaf styling rule on top of the table:
`notes_list[].match = 0` → attribute rendered red. Some `notes_list` rows carry
no `match` key at all.

### Narrowing loop

1. User toggles a spec or note in the comparison table.
2. **bom-log, call site 2 (S5)** — same payload shape; `entries` reflect the
   toggled spec selection. Fires **before** the custom replacement call.
3. **custom-replacement (S11)** — `POST /dev/new-search/custom-replacements`
   - Input: same identity fields as default-replacement, plus `specs[]`
     (`name`, `value`, `unit`) — the ticked subset only
   - Output: same shape as default-replacement (`main_data` + `notes_list` +
     `basic_spec_list` + `replace_list`)
4. Result re-renders through the spec list. The loop can repeat.
5. **save-user, call site 3 (S4)** — after the toggle
   - Input: same payload as call site 2, with
     `after_replacement_part_numbers` now filled
   - Output: `dataset_id`

---

## 7. Exit actions

Both terminal actions read from the spec list's row selection, so neither is
reachable if the comparison table does not render.

### Download (S12) — gated

1. **termsOfUse (N2)** — `GET api/v1/cad/termsOfUse`; input `lang`,
   `applicationId`, `sessionId`, `cadId`, `seriesCode`, `partNumber`; output
   `termsOfUseTypeList[]`. Consent gate; the CAD is not released until it passes.
2. **download CAD / list (S12)** — input rows shown in the spec list (`cadId`,
   `seriesCode`, `partNumber`); output CAD file or replacement list file.

### Order (S13 → S14) — leaves the application

1. **add to cart (S13)** — input rows shown in the spec list (part number,
   quantity); output a cart line on MISUMI EC.
2. **View in MISUMI website (S14)** — cart handoff to
   `stg1-kr.misumi-ec.com/order/cart`. Separate login, separate credentials.

---



## 8. Data layer

Six data-layer components underpin the classification and replacement searches:

- Postgres (S15)
- MongoDB (S16)
- S3 storage (S17)
- OpenSearch / GDB (S18)
- ETL process — XDB (S19)
- ETL process — GDB (S20)

The ETL processes assemble the reference data that classification matches
against and that the replacement searches read from. **The wiring between these
components and the individual modules is unconfirmed** and is deliberately not
asserted in the source diagram. Specifically unresolved: the role of MongoDB,
and how the two ETL processes feed Postgres and OpenSearch.

---

## 9. Linear traces

**Typed → clean match → order**
login → save-user 1 → part-number → Match → result page → bom-log 1 →
save-user 2 → default-replacement (+ EC type search) → spec list → add to cart →
MISUMI EC

**BOM → fuzzy match → corrected → download**
login → excel-upload → BOM column mapping → part-number → Fuzzy match →
correction module → result page → bom-log 1 → save-user 2 →
default-replacement (+ EC type search) → spec list → termsOfUse → download

**Typed → no match → edited → re-classified**
login → save-user 1 → part-number → No match → edit modal →
**part-number (again)** → any of the four cases → onward as above

**Typed → not unique → brand selected**
login → save-user 1 → part-number → Not unique → correction module →
result page → onward as above

**Narrowed custom search**
… → spec list → toggle specs → bom-log 2 → custom-replacement → spec list
(re-render) → save-user 3 → download or add to cart

**Restore a prior search**
login → user-history → history-list page → user-history (2nd site) →
user-restore → result page (classification skipped entirely)

---

## 11. Loop-back edges

- edit modal → part-number API (re-classification after manual edit)
- custom-replacement → spec list (re-render with the narrowed result set)

## 12. Leaf nodes

announcement-list, brand-list, EC type search, red highlight. These terminate;
nothing depends on their output.
