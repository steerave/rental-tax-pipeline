# rental-tax-pipeline — Project Context

This file is the source of truth for any Claude session working on this project. Read it before making changes.

## What this project does

End-to-end Python pipeline that turns a rental business's raw bank statements, credit card statements, and property-manager PDFs into accountant-ready Excel P&L workbooks. Built for Gamgee Properties LLC (Sarun Teeravechyan), which has both STR (short-term rental) and LTR (long-term rental) properties.

**GitHub:** https://github.com/steerave/rental-tax-pipeline (public, portfolio piece)

## Properties

### STR (4 properties, self-managed)
- **15 Belden** (Galena, IL)
- **27 Farmstead Dr** (Galena, IL)
- **20 Valleywood Ln** (Galena, IL)
- **17 Oak Glen** (Galena, IL)

### LTR (3 properties, managed by Rent QC LLC)
- **1015 39th St** (Bettendorf, IA) — 12 units (101-304)
- **1210 College Ave** (Davenport, IA) — duplex (1210, 1212)
- **308 Lincoln Ave** (Davenport, IA) — 2 units (lower, 1/2 upper)
  - **Important:** Rent QC uses "308 S Lincoln Ave" but the accountant template says "308 Lincoln Ave". A `property_aliases` config entry normalizes this.

## Data sources (per tax year)

| Source | Format | Location | What it provides |
|---|---|---|---|
| Chase Business Checking (acct 7552) | PDF statements (12/year) | `years/YYYY/inputs/*-statements-7552-.pdf` | All bank transactions (STR income deposits, expenses, transfers) |
| Chase Ink Business Credit Card (acct 1091) | PDF statements (13/year) | `years/YYYY/inputs/*-statements-1091-.pdf` | Business credit card charges. **Two cardholders: 1091 (Sarun) + 1109 (Margarete Claudy, business co-user)** |
| Rent QC owner statements | PDF reports (13/year, mid-month to mid-month) | `years/YYYY/inputs/rentqc-*.pdf` | Pre-categorized LTR income + expenses with 28 category vocabulary |
| STR earnings Google Sheets | 4 Google Sheets (one per STR property) | Config: `str_sheets` in config.yaml | STR revenue per property. Tab naming: `'{YY} earnings`. **This is the source of truth for STR Sales revenue, NOT bank deposits.** |
| Interest expense YAML | `interest_expense.yaml` | Project root | Per-property mortgage interest from Form 1098. Manually filled. |
| Filed accountant workbooks | XLSX (STR + LTR) | `years/YYYY/outputs/` | The accountant's completed P&L from prior years. Used as templates and verification targets. |

### STR Google Sheet IDs
- 27 Farmstead Dr: `117nAsBcunTmuuxBB_qUh2rWxHlb8QprRyCWLpwgPtlQ`
- 15 Belden: `1HRihF2_ZWbXAajtDE68QowCLMSnqhOx0mGPfLgCGLGM`
- 20 Valleywood Ln: `11ul02uD-jaWVMNdxNU9qbApcSTSmPThBiSjyQh5UwtU`
- 17 Oak Glen: `16fbni_o58JYy8Htkf2xko5ecRKRqrNwa4XUoJILjSKM`

### Service account
`job-search-bot@job-search-tool-490420.iam.gserviceaccount.com` (reused from Job Search Tool project)
JSON key at: `C:\Users\steerave\Desktop\Claude Projects\Job Search Tool\service_account.json`
**Limitation:** Consumer Gmail service accounts can't create Drive files. Review Sheets must be pre-created by the user.

## Pipeline flow (CLI commands)

```
taxauto extract --year YYYY      # Parse all PDFs → intermediate JSON caches
taxauto categorize --year YYYY   # Apply vendor_mapping → auto-tag known, queue unknowns
taxauto review push --year YYYY  # Push vendor-grouped review queue to Google Sheet
  [user tags ~200-600 vendor rows in the Sheet]
taxauto review pull --year YYYY  # Read tags, resolve all transactions, update vendor_mapping
taxauto build --year YYYY        # Aggregate + write STR/LTR Excel workbooks
taxauto verify --year YYYY       # Compare generated output vs filed XLSX cell-by-cell
taxauto bootstrap --year YYYY    # Learn vendor mappings from Rent QC reports
```

## Review workflow (Phase 3 — current)

### How it works
1. `review push` creates two tabs on a Google Sheet:
   - **Vendors tab** (~574 unique vendors): one row per vendor, sorted by frequency. User fills in Category, Property, Expense Type.
   - **Transactions tab** (~1,085 transactions): all transactions for reference. User can override vendor-level decisions per-transaction.
2. User + Margarete tag vendors. `review pull` propagates vendor-level decisions to all matching transactions, with transaction-level overrides taking precedence.

### Current review Sheet
ID: `1l3pXIxVcb4NVjQO-oemSbnkkjU8JuJZF9Nz3BpDUgNM`
URL: https://docs.google.com/spreadsheets/d/1l3pXIxVcb4NVjQO-oemSbnkkjU8JuJZF9Nz3BpDUgNM

### Dropdown values

**Category (column G):** STR, LTR, Personal, Skip, Split, STR - Split, LTR - Split

**Property (column H):** 15 Belden, 27 Farmstead Dr, 20 Valleywood Ln, 17 Oak Glen, 1015 39th St, 1210 College Ave, 308 Lincoln Ave

**Expense Type (column I):** Advertising, Appliances, Bank Charges, Cleaning Fees, Commissions/Service Fees, Furniture and equipment, Insurance, Interest expense, Landscaping, Lawn and Snow Care, Licenses and Fees, Management Fees, Pest Control, Plumbing, Postages, Rent Expense, Renovations, Repairs and Maintenance, legal expenses, Supplies, Travel, Utilities, HOA, other

### Tagging rules (decided during Phase 3)

| Scenario | How to tag |
|---|---|
| Vendor serves one property | Category + Property + Expense Type on Vendors tab |
| Vendor serves multiple STR properties | Category=**STR - Split**, Property=(leave blank), Expense Type. Pipeline splits amount evenly across 4 STR properties. |
| Vendor serves multiple LTR properties | Category=**LTR - Split**, Property=(leave blank), Expense Type. Pipeline splits across 3 LTR. |
| Physical checks (no merchant info) | Leave Vendors tab blank. Tag each check in Transactions tab using Margarete's checkbook. |
| Credit card payments ("Payment Thank You") | **Auto-skipped** — filtered out during categorize step. |
| Airbnb/Vrbo bank deposits | **Auto-skipped** — STR revenue comes from Google Sheets, not bank. |
| Rent QC bank deposits | **Auto-skipped** — LTR income comes from Rent QC parser. |
| Etsy payouts | **Auto-skipped** — not rental income. |
| Etsy business expenses (Printify, Midjourney, eRank, Shopify, etc.) | Category=**Skip**. Etsy business is handled outside this pipeline. |
| Mortgage payments | Category=**Skip**. Interest is handled via `interest_expense.yaml`. |
| Owner transfers between accounts | Category=**Skip**. |

### Auto-skip patterns (in categorize step)
Checking deposits (positive amounts) containing: `airbnb`, `vrbo`, `rent qc`, `etsy`
Credit card entries containing: `payment thank you`

## Accountant template structure

### STR template (4 identical sheets, hardcoded rows)
Revenue: Sales revenue (D5), Laundry (D7), Late fees (D8), Other (D9). Total Revenues = formula at D10.
Expenses: rows 13-33 (Advertising, Appliances, ... Utilities, HOA, other). Total Expenses = formula at D34. Net Income = formula at D37.
**Quirk:** C33 must be forced to "other" (some sheets have it in wrong column).

### LTR template (3 sheets, DRIFTING row positions)
Same structure but row positions differ between 1015 39th St, 1210 College Ave, and 308 Lincoln Ave. The LTR writer scans column C per sheet to build a `{label: row}` map. Case-insensitive matching (e.g., "Lawn and Snow Care" vs "Lawn and Snow care").
**Do NOT hardcode LTR rows.** Always use `scan_label_rows()`.

## Key design decisions (locked)

1. **STR revenue = net of host fees** (bank payout amount). Commissions/Service Fees row stays blank.
2. **Transaction-date drives year assignment**, not filename. Rent QC reports filtered by `period_start.year == tax_year` then `txn.date.year == tax_year`.
3. **Rent QC → LTR template mapping** in `config.yaml` under `rentqc_to_ltr_template`. 28 Rent QC categories → template row labels. HVAC → Appliances. Reviewed by user.
4. **Double-count guard** matches Chase bank deposits from Rent QC to owner disbursement rows by eCheck reference (4-4 hex hash). Same reference shared across all 3 properties per month.
5. **Chase text pre-cleaner** must strip `*start*`/`*end*` anchors before any parsing. These are invisible PDF glyphs that pdfplumber splices into data lines.
6. **Credit card parser** has a cardholder state machine. Default `current_card = "1091"`, flips on `TRANSACTIONS THIS CYCLE (CARD xxxx)` subtotal lines.
7. **Writer copies 2024 workbooks as templates** (clears value cells, preserves formulas). Never writes to total/formula cells.

## Verification status (2024)

| Area | Status | Accuracy |
|---|---|---|
| STR Sales Revenue | Verified | 4/4 properties within $0.10 |
| LTR Rent QC → P&L | Verified | 59.5% cells within tolerance |
| LTR remaining gaps | Known | Renovations (manual), laundry/late fee timing, boundary effects |
| STR Expenses | Pending | Awaiting review Sheet tagging completion |
| Interest Expense | Pending | Awaiting `interest_expense.yaml` from Form 1098 |

## What's next

1. User finishes tagging ~574 vendor rows in the review Sheet
2. `taxauto review pull --year 2024` → `taxauto build --year 2024` → `taxauto verify --year 2024`
3. Fill `interest_expense.yaml` with Form 1098 values
4. Compare generated output vs filed 2024 and iterate on any discrepancies
5. Run 2025 pipeline (most vendors auto-tag from learned mappings)

## Test suite
134+ tests, 0 failures. Run: `.venv/Scripts/python.exe -m pytest -q`

## Reference documents
- Phase 1 plan: `C:\Users\steerave\.claude\plans\zesty-dancing-cosmos.md`
- Phase 2 plan: `C:\Users\steerave\.claude\plans\plucky-parsing-phoenix.md`
- Phase 3 plan: `C:\Users\steerave\.claude\plans\phase3-smart-review.md`
- Phase 3 spec: `docs/phase3-review-workflow-spec.md`
- Discovery reports: `years/2024/intermediate/discovery_*.md`
- Daily status: `docs/status.md`
