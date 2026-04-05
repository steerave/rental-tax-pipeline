"""Command-line entry point for taxauto.

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
from pathlib import Path
from typing import Any, Dict, List, Optional

from taxauto import _serialize as S
from taxauto.bootstrap.learn_from_prior import match_and_learn, read_prior_entries_xlsx
from taxauto.categorize.learning import (
    load_vendor_mapping,
    record_review_decisions,
    save_vendor_mapping,
)
from taxauto.categorize.mapper import categorize_transactions
from taxauto.config import Config, YearPaths, load_config
from taxauto.guards.duplicates import detect_duplicates
from taxauto.guards.reconcile import reconcile_statement
from taxauto.parsers.bank import parse_bank_text
from taxauto.parsers.pm_ltr import parse_pm_ltr_text
from taxauto.pdf.extractor import extract_pdf
from taxauto.writers.ltr_writer import write_ltr_workbook
from taxauto.writers.str_writer import write_str_workbook


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


# -------------------------------------------------------------------------
# Commands
# -------------------------------------------------------------------------

def cmd_extract(cfg: Config, year: int) -> int:
    paths = cfg.paths_for_year(year)

    bank_txns = []
    bank_inputs = paths.bank_inputs
    if bank_inputs.exists():
        for pdf in sorted(bank_inputs.glob("*.pdf")):
            doc = extract_pdf(pdf)
            result = parse_bank_text(
                doc.full_text,
                account=pdf.stem,
                statement_year=year,
            )
            reconcile_statement(result)  # fails loudly on mismatch
            bank_txns.extend(result.transactions)

    # Global duplicate check across all parsed bank files.
    dup_groups = detect_duplicates(bank_txns)
    if dup_groups:
        print(
            f"[extract] WARNING: {len(dup_groups)} duplicate transaction group(s) detected",
            file=sys.stderr,
        )

    pm_entries = []
    pm_inputs = paths.pm_ltr_inputs
    if pm_inputs.exists():
        for pdf in sorted(pm_inputs.glob("*.pdf")):
            doc = extract_pdf(pdf)
            result = parse_pm_ltr_text(doc.full_text, property_id=pdf.stem)
            pm_entries.extend(result.entries)

    _write_json(_cache_path(paths, "bank_transactions.json"), S.txns_to_list(bank_txns))
    _write_json(_cache_path(paths, "pm_ltr_entries.json"), S.pm_list_to_list(pm_entries))
    print(f"[extract] {len(bank_txns)} bank txns, {len(pm_entries)} PM entries cached for {year}")
    return 0


def cmd_categorize(cfg: Config, year: int) -> int:
    paths = cfg.paths_for_year(year)
    vendor_mapping = load_vendor_mapping(cfg.project_root / DEFAULT_VENDOR_MAPPING)

    bank_txns = S.list_to_txns(_read_json(_cache_path(paths, "bank_transactions.json")))

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


def _merge_auto_and_decisions(
    paths: YearPaths,
) -> List[Dict[str, Any]]:
    """Return a combined list of tagged-transaction dicts for the writer stage.

    Auto-tagged rows come straight from categorize. For each review decision,
    we look up the matching transaction in the review queue and rebuild a
    TaggedTransaction dict with the human-assigned category.
    """
    auto = _read_json(_cache_path(paths, "auto_tagged.json"))

    review_queue_path = _cache_path(paths, "review_queue.json")
    decisions_path = _cache_path(paths, "review_decisions.json")

    combined: List[Dict[str, Any]] = list(auto)

    if review_queue_path.exists() and decisions_path.exists():
        queue = _read_json(review_queue_path)
        decisions = _read_json(decisions_path)
        # Map queue rows by their (date, description, amount) fingerprint.
        fingerprint = {
            (
                q["transaction"]["date"],
                q["transaction"]["description"],
                q["transaction"]["amount"],
            ): q
            for q in queue
        }
        for d in decisions:
            key = (d.get("date", ""), d.get("description", ""), str(d.get("amount", "")))
            source = fingerprint.get(key)
            if source is None:
                continue
            if d["category"] in ("Skip", "Split"):
                # Skip: excluded from output. Split: Phase 2 workflow.
                continue
            merged = dict(source)
            merged["category"] = d["category"]
            merged["confidence"] = 1.0
            merged["source"] = "review"
            combined.append(merged)

    return combined


def cmd_build(cfg: Config, year: int) -> int:
    paths = cfg.paths_for_year(year)

    combined_dicts = _merge_auto_and_decisions(paths)
    tagged = [S.dict_to_tagged(d) for d in combined_dicts]

    pm_entries = S.list_to_pm_list(
        _read_json(_cache_path(paths, "pm_ltr_entries.json"))
    )

    paths.outputs.mkdir(parents=True, exist_ok=True)
    str_out = paths.outputs / f"str_{year}.xlsx"
    ltr_out = paths.outputs / f"ltr_{year}.xlsx"

    write_str_workbook(
        template_path=cfg.template_str,
        output_path=str_out,
        tagged_transactions=tagged,
    )
    write_ltr_workbook(
        template_path=cfg.template_ltr,
        output_path=ltr_out,
        tagged_transactions=tagged,
        pm_entries=pm_entries,
    )

    print(f"[build] wrote {str_out.name} and {ltr_out.name}")
    return 0


def cmd_bootstrap(cfg: Config, year: int) -> int:
    paths = cfg.paths_for_year(year)

    # Use cached bank txns if present; otherwise parse now.
    bank_cache = _cache_path(paths, "bank_transactions.json")
    if bank_cache.exists():
        bank_txns = S.list_to_txns(_read_json(bank_cache))
    else:
        bank_txns = []
        if paths.bank_inputs.exists():
            for pdf in sorted(paths.bank_inputs.glob("*.pdf")):
                doc = extract_pdf(pdf)
                bank_txns.extend(
                    parse_bank_text(doc.full_text, account=pdf.stem, statement_year=year).transactions
                )

    prior_entries = []
    str_xlsx = paths.outputs / f"str_{year}.xlsx"
    ltr_xlsx = paths.outputs / f"ltr_{year}.xlsx"
    if str_xlsx.exists():
        prior_entries.extend(read_prior_entries_xlsx(str_xlsx))
    if ltr_xlsx.exists():
        prior_entries.extend(read_prior_entries_xlsx(ltr_xlsx))

    vm_path = cfg.project_root / DEFAULT_VENDOR_MAPPING
    mapping = load_vendor_mapping(vm_path)
    report = match_and_learn(
        bank_txns,
        prior_entries,
        mapping,
        year=year,
        date_window_days=cfg.bootstrap_date_window_days,
        fuzzy_threshold=cfg.bootstrap_fuzzy_threshold,
    )
    save_vendor_mapping(vm_path, mapping)

    print(
        f"[bootstrap {year}] matched={report.matched} "
        f"new_vendors={report.new_vendors_learned} "
        f"ambiguous={report.ambiguous} "
        f"unmatched_bank={report.unmatched_bank}"
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
