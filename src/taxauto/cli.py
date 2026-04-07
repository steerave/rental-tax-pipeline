"""Command-line entry point for taxauto — Phase 3.

Subcommands:
    taxauto extract     --year YYYY
    taxauto categorize  --year YYYY
    taxauto review push --year YYYY
    taxauto review pull --year YYYY
    taxauto build       --year YYYY
    taxauto verify      --year YYYY
    taxauto bootstrap   --year YYYY

All commands are idempotent and share an on-disk JSON cache at
``years/YYYY/intermediate/``. Each step reads the previous step's cache and
writes its own, so any step can be re-run in isolation.
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, List, Optional

from taxauto import _serialize as S
from taxauto.config import Config, YearPaths, load_config


DEFAULT_CONFIG = "config.yaml"
DEFAULT_VENDOR_MAPPING = "vendor_mapping.yaml"


# -------------------------------------------------------------------------
# Cache helpers
# -------------------------------------------------------------------------

def _cache_path(paths: YearPaths, name: str) -> Path:
    paths.intermediate.mkdir(parents=True, exist_ok=True)
    return paths.intermediate / name


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _inputs_dir(cfg: Config, year: int) -> Path:
    """Resolve the flat inputs directory for a year."""
    return cfg.paths_for_year(year).inputs


# -------------------------------------------------------------------------
# Commands
# -------------------------------------------------------------------------

def cmd_extract(cfg: Config, year: int) -> int:
    """Classify input files and run format-specific parsers + reconciliation."""
    from taxauto.inputs.classifier import DocType, classify_directory
    from taxauto.parsers.chase_checking import parse_chase_checking
    from taxauto.parsers.chase_credit import parse_chase_credit
    from taxauto.parsers.rent_qc import parse_rent_qc_pdf
    from taxauto.guards.chase_reconcile import reconcile_chase_checking
    from taxauto.guards.rentqc_reconcile import reconcile_rent_qc_report
    from taxauto.pdf.extractor import extract_pdf

    paths = cfg.paths_for_year(year)
    inputs = _inputs_dir(cfg, year)

    groups = classify_directory(inputs)

    # 1. Chase checking
    all_checking_txns = []
    checking_pdfs = groups.get(DocType.CHASE_CHECKING, [])
    for pdf in checking_pdfs:
        doc = extract_pdf(pdf)
        stmt = parse_chase_checking(doc.full_text, account_label=pdf.stem)
        reconcile_chase_checking(stmt)
        all_txns = stmt.deposits + stmt.checks_paid + stmt.electronic_withdrawals + stmt.fees
        all_checking_txns.extend(all_txns)

    _write_json(
        _cache_path(paths, "chase_checking_txns.json"),
        S.chase_txns_to_list(all_checking_txns),
    )

    # 2. Chase credit card
    all_credit_txns = []
    credit_pdfs = groups.get(DocType.CHASE_CREDIT, [])
    for pdf in credit_pdfs:
        doc = extract_pdf(pdf)
        stmt = parse_chase_credit(doc.full_text, account_label="CC-1091")
        all_credit_txns.extend(stmt.transactions)

    _write_json(
        _cache_path(paths, "chase_credit_txns.json"),
        S.chase_credit_txns_to_list(all_credit_txns),
    )

    # 3. Rent QC
    all_reports = []
    total_rentqc_txns = 0
    rentqc_pdfs = groups.get(DocType.RENT_QC, [])
    for pdf in rentqc_pdfs:
        report = parse_rent_qc_pdf(pdf)
        reconcile_rent_qc_report(report)
        all_reports.append(report)
        for prop in report.properties:
            total_rentqc_txns += len(prop.transactions)

    _write_json(
        _cache_path(paths, "rentqc_reports.json"),
        S.rentqc_reports_to_list(all_reports),
    )

    print(
        f"[extract] {len(checking_pdfs)} checking PDFs ({len(all_checking_txns)} txns), "
        f"{len(credit_pdfs)} credit card PDFs ({len(all_credit_txns)} txns), "
        f"{len(rentqc_pdfs)} Rent QC PDFs ({total_rentqc_txns} txns)"
    )
    return 0


def cmd_categorize(cfg: Config, year: int) -> int:
    """Apply vendor mapping to checking + credit card transactions."""
    from taxauto.categorize.learning import load_vendor_mapping
    from taxauto.categorize.mapper import categorize_transactions
    from taxauto.parsers.bank import Transaction

    paths = cfg.paths_for_year(year)
    vendor_mapping = load_vendor_mapping(cfg.project_root / DEFAULT_VENDOR_MAPPING)

    # Load cached checking + credit transactions and convert to Phase 1
    # Transaction type for the categorizer (which expects bank.Transaction).
    checking = S.list_to_chase_txns(
        _read_json(_cache_path(paths, "chase_checking_txns.json"))
    )
    credit = S.list_to_chase_credit_txns(
        _read_json(_cache_path(paths, "chase_credit_txns.json"))
    )

    # Auto-skip known income deposits — these are already captured by
    # STR Google Sheets (Airbnb/Vrbo) or Rent QC parser (owner disbursements).
    _INCOME_DEPOSIT_PATTERNS = ["airbnb", "vrbo", "rent qc", "etsy"]
    _CC_SKIP_PATTERNS = ["payment thank you"]

    # Convert Chase types to bank.Transaction for the categorizer.
    bank_txns: List[Transaction] = []
    auto_skipped = 0
    for t in checking:
        # Skip positive-amount (deposit) transactions matching income sources
        if t.amount > 0 and any(p in t.description.lower() for p in _INCOME_DEPOSIT_PATTERNS):
            auto_skipped += 1
            continue
        bank_txns.append(Transaction(
            date=t.date,
            description=t.description,
            amount=t.amount,
            balance=None,
            account=t.account,
        ))
    for t in credit:
        if any(p in t.description.lower() for p in _CC_SKIP_PATTERNS):
            auto_skipped += 1
            continue
        bank_txns.append(Transaction(
            date=t.date,
            description=t.description,
            amount=t.amount,
            balance=None,
            account=t.account,
        ))

    result = categorize_transactions(
        bank_txns, vendor_mapping, min_confidence=cfg.bootstrap_min_confidence
    )

    _write_json(
        _cache_path(paths, "auto_tagged.json"),
        [S.tagged_to_dict(t) for t in result.auto_tagged],
    )
    _write_json(
        _cache_path(paths, "review_queue.json"),
        [S.tagged_to_dict(t) for t in result.review_queue],
    )
    print(
        f"[categorize] auto={len(result.auto_tagged)} "
        f"ambiguous={len(result.ambiguous)} unknown={len(result.unknown)} "
        f"auto_skipped={auto_skipped} (income deposits + CC payments)"
    )
    return 0


def cmd_review_push(cfg: Config, year: int, client_factory=None) -> int:
    """Create a new Google Sheet and push the vendor-grouped review queue."""
    from taxauto.sheets.client import get_sheets_client
    from taxauto.sheets.create import create_and_share_sheet
    from taxauto.sheets.push import push_review_queue

    paths = cfg.paths_for_year(year)
    queue_path = _cache_path(paths, "review_queue.json")
    if not queue_path.exists():
        print("[review push] No review_queue.json found. Run 'categorize' first.", file=sys.stderr)
        return 2

    queue_dicts = _read_json(queue_path)
    queue = [S.dict_to_tagged(d) for d in queue_dicts]
    if not queue:
        print("[review push] Review queue is empty — nothing to push.")
        return 0

    if not cfg.google_service_account_json:
        print("[review push] GOOGLE_SERVICE_ACCOUNT_JSON not set", file=sys.stderr)
        return 2

    sa_path = Path(cfg.google_service_account_json)

    if client_factory is None:
        client = get_sheets_client(sa_path)
    else:
        client = client_factory()

    # --- Margarete reconciliation (pre-fill from her expense worksheet) ---
    prefills = {}
    margarete_cfg = cfg.raw.get("margarete_sheet", {}) or {}
    margarete_sheet_id = margarete_cfg.get("sheet_id", "14l3vIA_t5RVRTZBeGQeAU0HIkT5W33YXQkD5eXtfQQo")
    margarete_tab = margarete_cfg.get("tab_name", f"{year} tax info")
    if margarete_sheet_id and sa_path.exists():
        try:
            from taxauto.reconcile.margarete_sheet import (
                load_margarete_sheet,
                reconcile_against_margarete,
            )
            print(f"[review push] Loading Margarete's expense worksheet...")
            marg_rows = load_margarete_sheet(sa_path, sheet_id=margarete_sheet_id, tab_name=margarete_tab)
            prefills = reconcile_against_margarete(queue_dicts, marg_rows)
            print(f"[review push] Matched {len(prefills)} of {len(queue)} review-queue items against Margarete's {len(marg_rows)} rows")
        except Exception as ex:
            print(f"[review push] Margarete reconciliation skipped: {ex}", file=sys.stderr)

    review_cfg = cfg.raw.get("review", {}) or {}
    editor_emails = review_cfg.get("editor_emails", [])
    sheet_name = review_cfg.get("sheet_name_template", "rental-tax-review-{year}").format(year=year)

    # Reuse an existing sheet if a cached ID or env var exists (service accounts
    # on free GCP projects have zero Drive storage and cannot create files).
    existing_id = None
    sheet_id_path = _cache_path(paths, "review_sheet_id.txt")
    if sheet_id_path.exists():
        existing_id = sheet_id_path.read_text(encoding="utf-8").strip()
    if not existing_id and cfg.review_sheet_id:
        existing_id = cfg.review_sheet_id

    spreadsheet = create_and_share_sheet(
        client,
        title=sheet_name,
        editor_emails=editor_emails,
        existing_sheet_id=existing_id,
    )
    print(f"[review push] Created Sheet: {spreadsheet.url}")

    all_properties = cfg.raw.get("all_properties", []) or []
    expense_types = cfg.raw.get("expense_types", []) or []

    # Use year-specific tab names so 2024 and 2025 can coexist
    vendor_tab = f"Vendors {year}"
    txn_tab = f"Transactions {year}"

    result = push_review_queue(
        spreadsheet,
        tagged_transactions=queue,
        categories=cfg.categories_primary,
        properties=all_properties,
        expense_types=expense_types,
        year=year,
        prefills=prefills,
        vendor_tab_name=vendor_tab,
        txn_tab_name=txn_tab,
    )

    # Cache the Sheet ID for the pull step
    sheet_id_path = _cache_path(paths, "review_sheet_id.txt")
    sheet_id_path.write_text(spreadsheet.id, encoding="utf-8")

    print(
        f"[review push] {result['vendor_count']} vendors, {result['txn_count']} transactions, "
        f"{result.get('prefilled', 0)} pre-filled from Margarete's worksheet"
    )
    return 0


def cmd_review_pull(cfg: Config, year: int, client_factory=None) -> int:
    """Pull vendor + transaction decisions, resolve all queue items, update vendor mapping."""
    from taxauto.sheets.client import get_sheets_client
    from taxauto.sheets.pull import pull_review_decisions
    from taxauto.categorize.learning import load_vendor_mapping, save_vendor_mapping
    from taxauto.categorize.mapper import normalize_vendor

    paths = cfg.paths_for_year(year)

    if not cfg.google_service_account_json:
        print("[review pull] GOOGLE_SERVICE_ACCOUNT_JSON not set", file=sys.stderr)
        return 2

    # Get Sheet ID
    sheet_id_path = _cache_path(paths, "review_sheet_id.txt")
    if sheet_id_path.exists():
        sheet_id = sheet_id_path.read_text(encoding="utf-8").strip()
    elif cfg.review_sheet_id:
        sheet_id = cfg.review_sheet_id
    else:
        print("[review pull] No Sheet ID found. Run 'review push' first.", file=sys.stderr)
        return 2

    if client_factory is None:
        client = get_sheets_client(Path(cfg.google_service_account_json))
    else:
        client = client_factory()

    spreadsheet = client.open_by_key(sheet_id)
    decisions = pull_review_decisions(spreadsheet, year=year)

    # Save raw decisions
    _write_json(_cache_path(paths, "review_decisions_raw.json"), decisions)

    # Resolve: apply vendor decisions to all review queue transactions
    queue = _read_json(_cache_path(paths, "review_queue.json"))
    resolved: list = []

    for i, td in enumerate(queue):
        txn = td.get("transaction", {})
        vendor_key = normalize_vendor(txn.get("description", ""))
        row_id = f"{year}-{i + 1:04d}"

        # Check for transaction-level override first
        override = decisions.get("transaction_overrides", {}).get(row_id)
        if override:
            resolved.append({
                "transaction": txn,
                "category": override["category"],
                "property": override.get("property", ""),
                "expense_type": override.get("expense_type", ""),
                "confidence": 1.0,
                "source": "review_override",
            })
            continue

        # Fall back to vendor-level decision
        vendor_decision = decisions["vendor_decisions"].get(vendor_key)
        if vendor_decision is None:
            continue

        resolved.append({
            "transaction": txn,
            "category": vendor_decision["category"],
            "property": vendor_decision.get("property", ""),
            "expense_type": vendor_decision.get("expense_type", ""),
            "confidence": 1.0,
            "source": "review_vendor",
        })

    _write_json(_cache_path(paths, "resolved_decisions.json"), resolved)

    # Update vendor_mapping
    vm_path = cfg.project_root / DEFAULT_VENDOR_MAPPING
    mapping = load_vendor_mapping(vm_path)
    vendors_map = mapping.setdefault("vendors", {})

    for vendor_key, vd in decisions["vendor_decisions"].items():
        if vd["category"] in ("Skip", "Split", "STR - Split", "LTR - Split"):
            continue
        entry = vendors_map.get(vendor_key)
        if entry is None:
            vendors_map[vendor_key] = {
                "category": vd["category"],
                "property": vd.get("property", ""),
                "expense_type": vd.get("expense_type", ""),
                "confidence": 0.9,
                "occurrences": vd.get("count", 1),
                "learned_from": [year],
                "ambiguous": False,
                "source": "review",
            }
        else:
            entry["occurrences"] = int(entry.get("occurrences", 0)) + vd.get("count", 1)
            if vd.get("property"):
                entry["property"] = vd["property"]
            if vd.get("expense_type"):
                entry["expense_type"] = vd["expense_type"]
            learned_from = entry.setdefault("learned_from", [])
            if year not in learned_from:
                learned_from.append(year)
            if entry.get("category") and entry["category"] != vd["category"]:
                entry["ambiguous"] = True
            else:
                entry["category"] = vd["category"]

    save_vendor_mapping(vm_path, mapping)

    skipped = sum(1 for vd in decisions["vendor_decisions"].values() if vd["category"] in ("Skip", "Split", "STR - Split", "LTR - Split"))
    print(
        f"[review pull] {len(decisions['vendor_decisions'])} vendors tagged "
        f"({skipped} skip/split), {len(decisions.get('transaction_overrides', {}))} overrides, "
        f"{len(resolved)} resolved"
    )
    return 0


def cmd_build(cfg: Config, year: int) -> int:
    """Aggregate all sources and write STR + LTR workbooks."""
    from taxauto.aggregate.by_property import aggregate_by_property
    from taxauto.guards.double_count import detect_double_counts
    from taxauto.sources.interest_expense import load_interest_expense
    from taxauto.sources.str_sheets import (
        load_str_earnings_from_gsheets,
        load_str_earnings_from_xlsx,
        total_net_payout_by_property,
    )
    from taxauto.writers.ltr_writer import write_ltr_workbook
    from taxauto.writers.str_writer import write_str_workbook
    from taxauto.writers.transactions_tab import append_transactions_tab

    paths = cfg.paths_for_year(year)

    # Load intermediate caches
    checking_txns = S.list_to_chase_txns(
        _read_json(_cache_path(paths, "chase_checking_txns.json"))
    )
    credit_txns = S.list_to_chase_credit_txns(
        _read_json(_cache_path(paths, "chase_credit_txns.json"))
    )
    rentqc_reports = S.list_to_rentqc_reports(
        _read_json(_cache_path(paths, "rentqc_reports.json"))
    )

    # Load auto-tagged + resolved review decisions (includes property + expense_type)
    auto_tagged_dicts = _read_json(_cache_path(paths, "auto_tagged.json"))
    resolved_path = _cache_path(paths, "resolved_decisions.json")
    resolved_decisions = _read_json(resolved_path) if resolved_path.exists() else []

    # Combine auto-tagged + resolved
    combined_tagged = list(auto_tagged_dicts)
    for rd in resolved_decisions:
        cat = rd.get("category", "")
        if cat in ("Skip", "Split", ""):
            continue
        combined_tagged.append(rd)

    # Load STR earnings — prefer live Google Sheets, fall back to XLSX
    str_earnings = []
    str_by_property = {}
    str_sheet_configs = cfg.raw.get("str_sheets") or {}
    if str_sheet_configs and cfg.google_service_account_json:
        sa_path = Path(cfg.google_service_account_json)
        if sa_path.exists():
            print(f"[build] loading STR earnings from {len(str_sheet_configs)} Google Sheets...")
            str_earnings = load_str_earnings_from_gsheets(
                str_sheet_configs,
                service_account_json=sa_path,
                year=year,
            )
            str_by_property = total_net_payout_by_property(str_earnings)
            for prop, total in sorted(str_by_property.items()):
                print(f"  {prop}: ${total:,.2f}")
        else:
            print(f"[build] service account not found at {sa_path}, trying XLSX fallback")
    if not str_earnings:
        str_xlsx_path = _inputs_dir(cfg, year) / "str_earnings.xlsx"
        if str_xlsx_path.exists():
            str_earnings = load_str_earnings_from_xlsx(str_xlsx_path)
            str_by_property = total_net_payout_by_property(str_earnings)

    # Load interest expense
    interest_path = cfg.project_root / "interest_expense.yaml"
    interest_by_property = load_interest_expense(interest_path, year=year)

    # Load property aliases from config
    property_aliases = cfg.raw.get("property_aliases", {}) or {}

    # Flatten all Rent QC transactions for double-count guard
    all_rentqc_txns = []
    for report in rentqc_reports:
        if report.period_start and report.period_start.year != year:
            continue
        for prop in report.properties:
            normalized_name = property_aliases.get(prop.name, prop.name)
            for txn in prop.transactions:
                if txn.date.year != year:
                    continue
                all_rentqc_txns.append((normalized_name, txn))

    # eCheck double-count guard: find bank deposits that match owner disbursements
    all_rentqc_flat = [txn for _, txn in all_rentqc_txns]
    checking_deposits = [t for t in checking_txns if t.amount > 0]
    double_counts = detect_double_counts(checking_deposits, all_rentqc_flat)
    double_counted_descriptions = set()
    for dc in double_counts:
        # Mark the bank deposit so we can exclude it from LTR aggregation
        double_counted_descriptions.add(
            (dc.bank_transaction.date.isoformat(), dc.bank_transaction.description, str(dc.bank_transaction.amount))
        )
    if double_counts:
        print(f"[build] {len(double_counts)} eCheck double-count(s) excluded")

    # --- Build LTR totals from Cash Flow 12-Month summaries ---
    from taxauto.parsers.rentqc_cashflow import parse_cashflow_summaries

    cashflow_mapping = cfg.raw.get("cashflow_to_ltr_template", {}) or {}

    ltr_items = []

    # Find Cash Flow summaries from all Rent QC PDFs for this year
    from taxauto.inputs.classifier import DocType, classify_directory
    inputs = _inputs_dir(cfg, year)
    groups = classify_directory(inputs)

    # Only use the Cash Flow summary whose period is exactly Jan-Dec of the tax year
    # (e.g., "Jan 2024 to Dec 2024"). Other PDFs have rolling 12-month windows
    # that span two calendar years.
    expected_period = f"Jan {year} to Dec {year}"
    cashflow_summaries = []
    for pdf in groups.get(DocType.RENT_QC, []):
        summaries = parse_cashflow_summaries(pdf)
        for s in summaries:
            if (s.period or "") == expected_period:
                cashflow_summaries.append(s)

    if not cashflow_summaries:
        print(f"[build] WARNING: No Cash Flow 12-Month summaries found for {year}")

    for summary in cashflow_summaries:
        prop_name = property_aliases.get(summary.property_name, summary.property_name)

        # Income items
        for category, amount in summary.income.items():
            template_cat = cashflow_mapping.get(category)
            if template_cat is None:
                continue
            ltr_items.append({
                "property": prop_name,
                "template_category": template_cat,
                "amount": amount,  # positive for income
            })

        # Expense items
        for category, amount in summary.expenses.items():
            template_cat = cashflow_mapping.get(category)
            if template_cat is None:
                continue
            ltr_items.append({
                "property": prop_name,
                "template_category": template_cat,
                "amount": -amount,  # negative for expenses (aggregator flips)
            })

    print(f"[build] {len(cashflow_summaries)} Cash Flow summaries loaded")

    # b) Interest expense per property (for LTR properties)
    for prop_name, interest in interest_by_property.items():
        ltr_items.append({
            "property": prop_name,
            "template_category": "Interest expense",
            "amount": -interest,  # expense stored as negative for aggregator
        })

    # Property groups for split logic
    STR_PROPERTIES = ["15 Belden", "27 Farmstead Dr", "20 Valleywood Ln", "17 Oak Glen"]
    LTR_PROPERTIES = ["1015 39th St", "1210 College Ave", "308 Lincoln Ave"]

    # c) Bank/credit card tagged "LTR" or "LTR - Split" from review (excluding double-counted)
    for td in combined_tagged:
        cat = td.get("category", "")
        if cat not in ("LTR", "LTR - Split"):
            continue
        txn_d = td.get("transaction", {})
        key = (txn_d.get("date", ""), txn_d.get("description", ""), txn_d.get("amount", ""))
        if key in double_counted_descriptions:
            continue
        prop = td.get("property", "")
        expense_type = td.get("expense_type", "other")
        amount = Decimal(str(txn_d.get("amount", "0")))
        if cat == "LTR - Split":
            split_amount = amount / len(LTR_PROPERTIES)
            for split_prop in LTR_PROPERTIES:
                ltr_items.append({
                    "property": split_prop,
                    "template_category": expense_type,
                    "amount": split_amount,
                })
        elif prop:
            ltr_items.append({
                "property": prop,
                "template_category": expense_type,
                "amount": amount,
            })

    ltr_totals = aggregate_by_property(ltr_items)

    # --- Build STR totals ---
    str_items = []

    # a) Sales revenue per property from STR earnings
    for prop_name, net in str_by_property.items():
        str_items.append({
            "property": prop_name,
            "template_category": "Sales revenue",
            "amount": net,
        })

    # b) STR expenses from categorized bank/CC transactions
    for td in combined_tagged:
        cat = td.get("category", "")
        if cat not in ("STR", "STR - Split"):
            continue
        txn_d = td.get("transaction", {})
        prop = td.get("property", "")
        expense_type = td.get("expense_type", "other")
        amount = Decimal(str(txn_d.get("amount", "0")))
        if cat == "STR - Split":
            split_amount = amount / len(STR_PROPERTIES)
            for split_prop in STR_PROPERTIES:
                str_items.append({
                    "property": split_prop,
                    "template_category": expense_type,
                    "amount": split_amount,
                })
        elif prop:
            str_items.append({
                "property": prop,
                "template_category": expense_type,
                "amount": amount,
            })

    # c) Interest expense for STR properties
    # (STR interest if applicable - configurable per property)

    str_totals = aggregate_by_property(str_items)

    # --- Write workbooks ---
    paths.outputs.mkdir(parents=True, exist_ok=True)

    # Template paths
    str_template = cfg.template_str
    ltr_template = cfg.template_ltr

    str_out = paths.outputs / f"{year} - STR - Income Expense summary_generated.xlsx"
    ltr_out = paths.outputs / f"{year} - LTR - Income Expense summary_generated.xlsx"

    if str_template.exists():
        write_str_workbook(
            template_path=str_template,
            output_path=str_out,
            per_property_totals=str_totals,
            year=year,
        )
        print(f"[build] wrote {str_out.name}")
    else:
        print(f"[build] STR template not found: {str_template}", file=sys.stderr)

    if ltr_template.exists():
        write_ltr_workbook(
            template_path=ltr_template,
            output_path=ltr_out,
            per_property_totals=ltr_totals,
            year=year,
        )
        print(f"[build] wrote {ltr_out.name}")
    else:
        print(f"[build] LTR template not found: {ltr_template}", file=sys.stderr)

    # Append transactions tabs (audit trail using transaction-level data)
    from taxauto.aggregate.rentqc_to_template import get_rentqc_mapping, map_rentqc_category
    rentqc_mapping = get_rentqc_mapping(cfg)
    ltr_detail = {}  # property -> [txn dicts]
    for prop_name, txn in all_rentqc_txns:
        if not txn.category:
            continue
        template_cat = map_rentqc_category(txn.category, rentqc_mapping)
        if template_cat is None:
            continue
        amount = txn.cash_in if txn.cash_in else (txn.cash_out if txn.cash_out else Decimal("0"))
        ltr_detail.setdefault(prop_name, []).append({
            "date": txn.date.isoformat(),
            "source": "rentqc",
            "description": txn.description,
            "amount": amount,
            "template_category": template_cat,
            "notes": f"payee={txn.payee}",
        })

    if ltr_out.exists():
        for prop_name, txn_list in ltr_detail.items():
            append_transactions_tab(ltr_out, sheet_name=prop_name, transactions=txn_list)

    print(f"[build] done for {year}")
    return 0


def cmd_verify(cfg: Config, year: int) -> int:
    """Compare generated output against filed XLSX and print a delta report."""
    from taxauto.verify.compare import compare_workbooks, format_comparison_table

    paths = cfg.paths_for_year(year)

    # STR comparison
    str_generated = paths.outputs / f"{year} - STR - Income Expense summary_generated.xlsx"
    str_filed = paths.outputs / f"{year} - STR - Income Expense summary .xlsx"
    if not str_filed.exists():
        str_filed = paths.outputs / f"{year} - STR - Income Expense summary.xlsx"

    if str_generated.exists() and str_filed.exists():
        print("\n=== STR Comparison ===")
        results = compare_workbooks(str_filed, str_generated)
        print(format_comparison_table(results))
    else:
        print("[verify] STR: filed or generated workbook not found")
        print(f"  filed:     {str_filed}")
        print(f"  generated: {str_generated}")

    # LTR comparison
    ltr_generated = paths.outputs / f"{year} - LTR - Income Expense summary_generated.xlsx"
    ltr_filed = paths.outputs / f"LTR- Income Expense summary{year}.xlsx"

    if ltr_generated.exists() and ltr_filed.exists():
        print("\n=== LTR Comparison ===")
        results = compare_workbooks(ltr_filed, ltr_generated)
        print(format_comparison_table(results))
    else:
        print("[verify] LTR: filed or generated workbook not found")
        print(f"  filed:     {ltr_filed}")
        print(f"  generated: {ltr_generated}")

    return 0


def cmd_bootstrap(cfg: Config, year: int) -> int:
    """Learn vendor mappings from Rent QC owner statements."""
    from taxauto.parsers.rent_qc import parse_rent_qc_pdf
    from taxauto.bootstrap.learn_from_rentqc import learn_vendors_from_rentqc
    from taxauto.categorize.learning import load_vendor_mapping, save_vendor_mapping

    inputs = _inputs_dir(cfg, year)
    from taxauto.inputs.classifier import DocType, classify_directory
    groups = classify_directory(inputs)

    # Parse all Rent QC PDFs
    reports = []
    for pdf in groups.get(DocType.RENT_QC, []):
        report = parse_rent_qc_pdf(pdf)
        reports.append(report)

    vm_path = cfg.project_root / DEFAULT_VENDOR_MAPPING
    mapping = load_vendor_mapping(vm_path)

    result = learn_vendors_from_rentqc(reports, mapping, year=year)
    save_vendor_mapping(vm_path, mapping)

    print(
        f"[bootstrap {year}] transactions={result.total_transactions} "
        f"categories_seen={result.categories_seen} "
        f"vendors_learned={result.vendors_learned}"
    )
    return 0


# -------------------------------------------------------------------------
# Argument parsing
# -------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="taxauto")
    p.add_argument("--config", default=DEFAULT_CONFIG, help="Path to config.yaml")
    sub = p.add_subparsers(dest="command", required=True)

    def add_year(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--year", type=int, required=True)

    add_year(sub.add_parser("extract"))
    add_year(sub.add_parser("categorize"))
    add_year(sub.add_parser("build"))
    add_year(sub.add_parser("verify"))
    add_year(sub.add_parser("bootstrap"))

    review = sub.add_parser("review")
    review_sub = review.add_subparsers(dest="review_command", required=True)
    add_year(review_sub.add_parser("push"))
    add_year(review_sub.add_parser("pull"))

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    cfg = load_config(Path(args.config))
    year = args.year

    if args.command == "extract":
        return cmd_extract(cfg, year)
    if args.command == "categorize":
        return cmd_categorize(cfg, year)
    if args.command == "build":
        return cmd_build(cfg, year)
    if args.command == "verify":
        return cmd_verify(cfg, year)
    if args.command == "bootstrap":
        return cmd_bootstrap(cfg, year)
    if args.command == "review":
        if args.review_command == "push":
            return cmd_review_push(cfg, year)
        if args.review_command == "pull":
            return cmd_review_pull(cfg, year)

    parser.error("unknown command")
    return 2
