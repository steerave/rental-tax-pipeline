"""Command-line entry point for taxauto — Phase 2.

Subcommands:
    taxauto extract     --year YYYY
    taxauto categorize  --year YYYY
    taxauto review push --year YYYY
    taxauto review pull --year YYYY
    taxauto build       --year YYYY
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
        all_txns = stmt.deposits + stmt.checks_paid + stmt.electronic_withdrawals
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

    # Convert Chase types to bank.Transaction for the categorizer.
    bank_txns: List[Transaction] = []
    for t in checking:
        bank_txns.append(Transaction(
            date=t.date,
            description=t.description,
            amount=t.amount,
            balance=None,
            account=t.account,
        ))
    for t in credit:
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
        f"ambiguous={len(result.ambiguous)} unknown={len(result.unknown)}"
    )
    return 0


def cmd_review_push(cfg: Config, year: int, client_factory=None) -> int:
    from taxauto.sheets.client import get_sheets_client
    from taxauto.sheets.push import push_review_queue

    paths = cfg.paths_for_year(year)
    queue = [S.dict_to_tagged(d) for d in _read_json(_cache_path(paths, "review_queue.json"))]

    if not cfg.review_sheet_id or not cfg.google_service_account_json:
        print("[review push] REVIEW_SHEET_ID or GOOGLE_SERVICE_ACCOUNT_JSON not set", file=sys.stderr)
        return 2

    if client_factory is None:
        client = get_sheets_client(Path(cfg.google_service_account_json))
    else:
        client = client_factory()

    row_ids = push_review_queue(
        client,
        sheet_id=cfg.review_sheet_id,
        tagged_transactions=queue,
        categories=cfg.categories_primary,
        year=year,
    )
    print(f"[review push] pushed {len(row_ids)} rows for {year}")
    return 0


def cmd_review_pull(cfg: Config, year: int, client_factory=None) -> int:
    from taxauto.sheets.client import get_sheets_client
    from taxauto.sheets.pull import pull_review_decisions
    from taxauto.categorize.learning import (
        load_vendor_mapping,
        record_review_decisions,
        save_vendor_mapping,
    )

    paths = cfg.paths_for_year(year)

    if not cfg.review_sheet_id or not cfg.google_service_account_json:
        print("[review pull] REVIEW_SHEET_ID or GOOGLE_SERVICE_ACCOUNT_JSON not set", file=sys.stderr)
        return 2

    if client_factory is None:
        client = get_sheets_client(Path(cfg.google_service_account_json))
    else:
        client = client_factory()

    decisions = pull_review_decisions(client, sheet_id=cfg.review_sheet_id, year=year)
    _write_json(_cache_path(paths, "review_decisions.json"), decisions)

    # Fold decisions into the global vendor mapping.
    vm_path = cfg.project_root / DEFAULT_VENDOR_MAPPING
    mapping = load_vendor_mapping(vm_path)
    record_review_decisions(mapping, decisions)
    save_vendor_mapping(vm_path, mapping)

    print(f"[review pull] pulled {len(decisions)} decisions for {year}")
    return 0


def cmd_build(cfg: Config, year: int) -> int:
    """Aggregate all sources and write STR + LTR workbooks."""
    from taxauto.aggregate.by_property import aggregate_by_property
    from taxauto.aggregate.rentqc_to_template import get_rentqc_mapping, map_rentqc_category
    from taxauto.guards.double_count import detect_double_counts
    from taxauto.sources.interest_expense import load_interest_expense
    from taxauto.sources.str_sheets import load_str_earnings_from_xlsx, total_net_payout_by_property
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

    # Load auto-tagged + review decisions
    auto_tagged_dicts = _read_json(_cache_path(paths, "auto_tagged.json"))
    review_decisions_path = _cache_path(paths, "review_decisions.json")
    review_decisions = _read_json(review_decisions_path) if review_decisions_path.exists() else []

    # Merge auto-tagged and review decisions into a combined list
    combined_tagged = list(auto_tagged_dicts)

    review_queue_path = _cache_path(paths, "review_queue.json")
    if review_queue_path.exists() and review_decisions:
        queue = _read_json(review_queue_path)
        fingerprint = {
            (
                q["transaction"]["date"],
                q["transaction"]["description"],
                q["transaction"]["amount"],
            ): q
            for q in queue
        }
        for d in review_decisions:
            key = (d.get("date", ""), d.get("description", ""), str(d.get("amount", "")))
            source = fingerprint.get(key)
            if source is None:
                continue
            if d["category"] in ("Skip", "Split"):
                continue
            merged = dict(source)
            merged["category"] = d["category"]
            merged["confidence"] = 1.0
            merged["source"] = "review"
            combined_tagged.append(merged)

    # Load STR earnings
    str_xlsx_path = _inputs_dir(cfg, year) / "str_earnings.xlsx"
    str_earnings = []
    str_by_property = {}
    if str_xlsx_path.exists():
        str_earnings = load_str_earnings_from_xlsx(str_xlsx_path)
        str_by_property = total_net_payout_by_property(str_earnings)

    # Load interest expense
    interest_path = cfg.project_root / "interest_expense.yaml"
    interest_by_property = load_interest_expense(interest_path, year=year)

    # Rent QC category mapping
    rentqc_mapping = get_rentqc_mapping(cfg)

    # Load property aliases from config
    property_aliases = cfg.raw.get("property_aliases", {}) or {}

    # Flatten all Rent QC transactions, filtering by report period and
    # normalizing property names via aliases.
    # Include reports whose period_start.year == tax year, then from those
    # reports only include transactions whose date.year == tax year.
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

    # --- Build LTR totals ---
    ltr_items = []

    # a) Rent QC transactions -> template categories
    for prop_name, txn in all_rentqc_txns:
        if not txn.category:
            continue
        template_cat = map_rentqc_category(txn.category, rentqc_mapping)
        if template_cat is None:
            continue
        # Use cash_in (positive) or cash_out (negative) as amount
        amount = txn.cash_in if txn.cash_in else (txn.cash_out if txn.cash_out else Decimal("0"))
        ltr_items.append({
            "property": prop_name,
            "template_category": template_cat,
            "amount": amount,
        })

    # b) Interest expense per property (for LTR properties)
    for prop_name, interest in interest_by_property.items():
        ltr_items.append({
            "property": prop_name,
            "template_category": "Interest expense",
            "amount": -interest,  # expense stored as negative for aggregator
        })

    # c) Bank/credit card tagged "LTR" from review (excluding double-counted)
    for td in combined_tagged:
        cat = td.get("category", "")
        if cat != "LTR":
            continue
        txn_d = td.get("transaction", {})
        key = (txn_d.get("date", ""), txn_d.get("description", ""), txn_d.get("amount", ""))
        if key in double_counted_descriptions:
            continue
        # These need a property and template_category from the review decision
        # For now, skip bank/CC LTR items that don't have property assignment
        # (they'll be handled in the full review workflow)

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

    # b) Bank/credit card tagged "STR" from categorization
    for td in combined_tagged:
        cat = td.get("category", "")
        if cat != "STR":
            continue
        # Same note: needs property + template_category from review

    # c) Interest expense for STR properties
    # (STR interest if applicable - configurable per property)

    str_totals = aggregate_by_property(str_items)

    # --- Write workbooks ---
    paths.outputs.mkdir(parents=True, exist_ok=True)

    # Template paths
    str_template = cfg.template_str
    ltr_template = cfg.template_ltr

    str_out = paths.outputs / f"{year} - STR - Income Expense summary.xlsx"
    ltr_out = paths.outputs / f"{year} - LTR - Income Expense summary.xlsx"

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

    # Append transactions tabs
    # Build per-property transaction detail dicts for audit trail
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
    if args.command == "bootstrap":
        return cmd_bootstrap(cfg, year)
    if args.command == "review":
        if args.review_command == "push":
            return cmd_review_push(cfg, year)
        if args.review_command == "pull":
            return cmd_review_pull(cfg, year)

    parser.error("unknown command")
    return 2
