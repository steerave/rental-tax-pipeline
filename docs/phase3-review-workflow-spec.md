# Phase 3: Smart Review Workflow — Design Spec

## Goal

Reduce the 1,410-transaction categorization burden to ~200 vendor-level decisions via a Google Sheet with smart grouping, then propagate those decisions back into the pipeline to produce complete STR + LTR P&L workbooks with expenses populated.

## Decisions (locked)

| Decision | Value |
|---|---|
| Review medium | Google Sheet (auto-created by pipeline) |
| Sheet editors | `steerave@gmail.com`, `mclaudy@gmail.com` |
| Grouping strategy | Two tabs: "Vendors" (~200 rows) + "Transactions" (1,410 rows for audit) |
| STR property attribution | Extra dropdown column in the Sheet (per-vendor default, per-transaction override) |
| Template category | Explicit dropdown column (STR/LTR expense row assignment, e.g., Utilities, Supplies) |
| Vendor learning | Every decision is written back to `vendor_mapping.yaml` with provenance |

## Sheet Layout

### Tab 1: "Vendors" (~200 rows)

| Column | Content | Editable? |
|---|---|---|
| A: Vendor | Normalized vendor name | No |
| B: Count | Number of transactions for this vendor | No |
| C: Total Amount | Sum of absolute amounts for this vendor | No |
| D: Sample Description | First transaction's full description | No |
| E: Sample Amount | First transaction's amount | No |
| F: Accounts | Comma-separated list of accounts (checking/CC) | No |
| G: **Category** | Dropdown: STR / LTR / Personal / Skip / Split | **Yes** |
| H: **Property** | Dropdown: all 7 properties (4 STR + 3 LTR) / (blank) | **Yes** |
| I: **Expense Type** | Dropdown: all template expense categories (Advertising, Appliances, ... Utilities, HOA, other) | **Yes** |
| J: Notes | Free text | **Yes** |

Sorted by Count descending (most-frequent vendors first).

### Tab 2: "Transactions" (1,410 rows)

| Column | Content | Editable? |
|---|---|---|
| A: Row ID | Deterministic ID (`2024-0001` etc.) | No |
| B: Date | Transaction date | No |
| C: Vendor | Normalized vendor name | No |
| D: Description | Full original description | No |
| E: Amount | Transaction amount | No |
| F: Account | Source account (checking stem / CC-1091) | No |
| G: **Category** | Initially empty; auto-filled from Vendors tab on pull. Override here for exceptions. | **Yes** |
| H: **Property** | Same as above — auto-filled, overridable | **Yes** |
| I: **Expense Type** | Same as above — auto-filled, overridable | **Yes** |
| J: Notes | Free text | **Yes** |

Sorted by vendor (grouped), then date within each vendor group.

### Dropdown validation values

- **Category**: `STR`, `LTR`, `Personal`, `Skip`, `Split`, `STR - Split`, `LTR - Split`
- **Property**: `15 Belden`, `27 Farmstead Dr`, `20 Valleywood Ln`, `17 Oak Glen`, `1015 39th St`, `1210 College Ave`, `308 Lincoln Ave` (blank = N/A or shared). Split options removed — use `STR - Split` / `LTR - Split` categories instead.
- **Expense Type**: `Advertising`, `Appliances`, `Bank Charges`, `Cleaning Fees`, `Commissions/Service Fees`, `Furniture and equipment`, `Insurance`, `Interest expense`, `Landscaping`, `Licenses and Fees`, `Management Fees`, `Pest Control`, `Rent Expense`, `Renovations`, `Repairs and Maintenance`, `legal expenses`, `Supplies`, `Travel`, `Utilities`, `HOA`, `other`

## Data Flow

### Push (`taxauto review push --year 2024`)

1. Load `review_queue.json` (1,410 transactions).
2. Normalize each transaction's description to a vendor key (reuse `normalize_vendor` from `categorize/mapper.py`).
3. Group by vendor key → ~200 groups.
4. Create a new Google Sheet via the service account. Name: `rental-tax-review-{year}`.
5. Share with configured editor emails.
6. Write "Vendors" tab: one row per vendor group, sorted by count desc.
7. Write "Transactions" tab: all 1,410 rows, sorted by vendor then date.
8. Apply dropdown validation to columns G, H, I on both tabs.
9. Print the Sheet URL so the user can open it.
10. Cache the Sheet ID to `years/{year}/intermediate/review_sheet_id.txt` for the pull step.

### Pull (`taxauto review pull --year 2024`)

1. Read the Sheet ID from cache (or from config/env).
2. Read the "Vendors" tab. For each tagged vendor row:
   - Record the (vendor, category, property, expense_type) decision.
   - Update `vendor_mapping.yaml` with the new mapping (category, property default, expense_type, learned_from year, confidence 0.9).
3. Read the "Transactions" tab. For each row with Category filled in:
   - If the row's Category/Property/ExpenseType differs from the vendor-level decision, record it as a transaction-level override.
4. Apply vendor-level decisions to ALL matching transactions in the review queue.
5. Apply transaction-level overrides (these take precedence).
6. Write `review_decisions.json` with the fully resolved decisions.
7. Save `vendor_mapping.yaml`.
8. Print summary: X vendors tagged, Y transaction-level overrides, Z total decisions.

### Build (`taxauto build --year 2024`)

No changes to the build command — it already reads `auto_tagged.json` + `review_decisions.json` and aggregates. The review decisions now include property and expense_type fields, which the aggregator uses directly.

One addition: the aggregator must map each decision's `expense_type` field to the template row label. If `expense_type` is filled (from the review), use it directly as the `template_category`. If blank, fall back to inferring from the vendor mapping or leaving it unmapped (→ "other").

## Vendor Mapping Learning

After pull, `vendor_mapping.yaml` entries grow:

```yaml
vendors:
  printify:
    category: STR
    property: "15 Belden"          # NEW: default STR property
    expense_type: "Supplies"       # NEW: default template row
    confidence: 0.9
    occurrences: 143
    learned_from: [2024]
    ambiguous: false
    source: review
```

In future years, vendors with a learned `category`, `property`, and `expense_type` will auto-tag — no review needed.

## Config Changes

Add to `config.yaml`:

```yaml
# Review workflow
review:
  editor_emails:
    - steerave@gmail.com
    - mclaudy@gmail.com
  sheet_name_template: "rental-tax-review-{year}"
```

Add to `.env.template`:

```
# Google Sheet ID for the review queue (auto-populated by review push)
REVIEW_SHEET_ID=
```

## Scope Boundary

**In scope:**
- Review push with vendor grouping + two-tab layout
- Review pull with vendor-level + transaction-level decision merging
- Vendor mapping learning (category + property + expense_type)
- Build command reading the new fields
- Dropdown validation on the Sheet

**Out of scope (Phase 4+):**
- "Split" transaction handling (tagged but not processed — manual for now)
- Automatic template-category inference from merchant description
- Historical vendor auto-correction (changing a 2024 decision retroactively)
- Renovations manual override YAML (separate from the review workflow)

## Success Criteria

1. `review push --year 2024` creates a Sheet, the user can open it, and sees ~200 vendor rows + 1,410 transaction rows with dropdowns.
2. After tagging ~200 vendor rows, `review pull --year 2024` reads all decisions and produces a complete `review_decisions.json`.
3. `build --year 2024` produces STR and LTR workbooks with expense rows populated from the review decisions.
4. `build` automatically compares the generated workbooks against the filed 2024 outputs (`years/2024/outputs/`) and prints a per-cell delta report (same format as Phase 2 verification: Sheet | Row | Label | Filed | Generated | Delta | Within tolerance?). This is the accuracy check — every expense row should be close to what the accountant filed.
5. `vendor_mapping.yaml` grows by ~200 entries (one per tagged vendor) with category, property, and expense_type.
6. Full test suite remains green (119+ tests).
