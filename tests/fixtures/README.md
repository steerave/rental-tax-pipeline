# Test Fixtures

Phase 2 parsers are tested against **anonymized** fixture files, not the real
personal tax documents. Real documents live in `years/YYYY/inputs/` and are
gitignored.

## What goes here

| Directory | Source | Content |
|---|---|---|
| `chase_checking/` | `years/2024/intermediate/_txt_7552/` | Pre-extracted text snippets, hand-anonymized (names, account numbers, property addresses replaced with placeholders) |
| `chase_credit/` | Anonymized 1091 text snippets | Same |
| `rent_qc/` | Anonymized Rent QC text snippets | Same |
| `str_sheets/` | Hand-crafted mini XLSX | Simulates the Google Sheets structure |
| `output_templates/` | Blank copies of the 2024 XLSX with values wiped | Used by writer tests |

## Anonymization rules

1. Real names → `John Smith`, `Jane Doe`
2. Real account numbers → `XXXX9999`
3. Real property addresses → `123 Main St`, `456 Oak Ave`
4. Real guest names → `Guest A`, `Guest B`
5. Real Vrbo/Airbnb IDs → `1111111`, `2222222`
6. Dollar amounts → **keep as-is**; they're not PII and the reconciliation
   tests need realistic numbers

Never commit real statements. Run `git diff --cached` before every commit
that touches `tests/fixtures/`.
