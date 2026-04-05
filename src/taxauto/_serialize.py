"""JSON serialization helpers for intermediate caches.

Keeps per-year cached data interoperable between CLI steps without forcing
every module to know about pydantic or dataclass-wizard.

Phase 2 adds serializers for ChaseTransaction, ChaseCreditTransaction,
RentQCTransaction, RentQCProperty, and RentQCReport.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from taxauto.categorize.mapper import TaggedTransaction
from taxauto.parsers.bank import Transaction
from taxauto.parsers.chase_checking import ChaseCheckingStatement, ChaseTransaction
from taxauto.parsers.chase_credit import ChaseCreditStatement, ChaseCreditTransaction
from taxauto.parsers.pm_ltr import PMEntry
from taxauto.parsers.rent_qc import RentQCProperty, RentQCReport, RentQCTransaction


# ---- Phase 1 (bank.Transaction) ------------------------------------------

def txn_to_dict(t: Transaction) -> Dict[str, Any]:
    return {
        "date": t.date.isoformat(),
        "description": t.description,
        "amount": str(t.amount),
        "balance": str(t.balance) if t.balance is not None else None,
        "account": t.account,
    }


def dict_to_txn(d: Dict[str, Any]) -> Transaction:
    return Transaction(
        date=date.fromisoformat(d["date"]),
        description=d["description"],
        amount=Decimal(d["amount"]),
        balance=Decimal(d["balance"]) if d.get("balance") is not None else None,
        account=d["account"],
    )


# ---- Phase 1 (pm_ltr.PMEntry) --------------------------------------------

def pm_to_dict(e: PMEntry) -> Dict[str, Any]:
    return {
        "date": e.date.isoformat(),
        "description": e.description,
        "pm_category": e.pm_category,
        "amount": str(e.amount),
        "property_id": e.property_id,
    }


def dict_to_pm(d: Dict[str, Any]) -> PMEntry:
    return PMEntry(
        date=date.fromisoformat(d["date"]),
        description=d["description"],
        pm_category=d["pm_category"],
        amount=Decimal(d["amount"]),
        property_id=d["property_id"],
    )


# ---- TaggedTransaction ----------------------------------------------------

def tagged_to_dict(tt: TaggedTransaction) -> Dict[str, Any]:
    return {
        "transaction": txn_to_dict(tt.transaction),
        "category": tt.category,
        "confidence": tt.confidence,
        "source": tt.source,
    }


def dict_to_tagged(d: Dict[str, Any]) -> TaggedTransaction:
    return TaggedTransaction(
        transaction=dict_to_txn(d["transaction"]),
        category=d.get("category", ""),
        confidence=float(d.get("confidence", 0.0)),
        source=d.get("source", "unknown"),
    )


# ---- Convenience wrappers ------------------------------------------------

def txns_to_list(txns: Iterable[Transaction]) -> List[Dict[str, Any]]:
    return [txn_to_dict(t) for t in txns]


def list_to_txns(items: Iterable[Dict[str, Any]]) -> List[Transaction]:
    return [dict_to_txn(d) for d in items]


def pm_list_to_list(entries: Iterable[PMEntry]) -> List[Dict[str, Any]]:
    return [pm_to_dict(e) for e in entries]


def list_to_pm_list(items: Iterable[Dict[str, Any]]) -> List[PMEntry]:
    return [dict_to_pm(d) for d in items]


# =========================================================================
# Phase 2: Chase Checking
# =========================================================================

def chase_txn_to_dict(t: ChaseTransaction) -> Dict[str, Any]:
    return {
        "date": t.date.isoformat(),
        "description": t.description,
        "amount": str(t.amount),
        "account": t.account,
        "section": t.section,
        "check_number": t.check_number,
    }


def dict_to_chase_txn(d: Dict[str, Any]) -> ChaseTransaction:
    return ChaseTransaction(
        date=date.fromisoformat(d["date"]),
        description=d["description"],
        amount=Decimal(d["amount"]),
        account=d["account"],
        section=d["section"],
        check_number=d.get("check_number"),
    )


def chase_stmt_to_dict(s: ChaseCheckingStatement) -> Dict[str, Any]:
    return {
        "account": s.account,
        "period_start": s.period_start.isoformat() if s.period_start else None,
        "period_end": s.period_end.isoformat() if s.period_end else None,
        "beginning_balance": str(s.beginning_balance) if s.beginning_balance is not None else None,
        "ending_balance": str(s.ending_balance) if s.ending_balance is not None else None,
        "total_deposits": str(s.total_deposits) if s.total_deposits is not None else None,
        "total_checks_paid": str(s.total_checks_paid) if s.total_checks_paid is not None else None,
        "total_electronic_withdrawals": str(s.total_electronic_withdrawals) if s.total_electronic_withdrawals is not None else None,
        "deposits": [chase_txn_to_dict(t) for t in s.deposits],
        "checks_paid": [chase_txn_to_dict(t) for t in s.checks_paid],
        "electronic_withdrawals": [chase_txn_to_dict(t) for t in s.electronic_withdrawals],
    }


# =========================================================================
# Phase 2: Chase Credit Card
# =========================================================================

def chase_credit_txn_to_dict(t: ChaseCreditTransaction) -> Dict[str, Any]:
    return {
        "date": t.date.isoformat(),
        "description": t.description,
        "amount": str(t.amount),
        "cardholder_last4": t.cardholder_last4,
        "account": t.account,
    }


def dict_to_chase_credit_txn(d: Dict[str, Any]) -> ChaseCreditTransaction:
    return ChaseCreditTransaction(
        date=date.fromisoformat(d["date"]),
        description=d["description"],
        amount=Decimal(d["amount"]),
        cardholder_last4=d["cardholder_last4"],
        account=d["account"],
    )


# =========================================================================
# Phase 2: Rent QC
# =========================================================================

def _opt_decimal(v: Optional[Decimal]) -> Optional[str]:
    return str(v) if v is not None else None


def _from_opt_decimal(v: Optional[str]) -> Optional[Decimal]:
    return Decimal(v) if v is not None else None


def rentqc_txn_to_dict(t: RentQCTransaction) -> Dict[str, Any]:
    return {
        "date": t.date.isoformat(),
        "payee": t.payee,
        "txn_type": t.txn_type,
        "reference": t.reference,
        "description": t.description,
        "cash_in": _opt_decimal(t.cash_in),
        "cash_out": _opt_decimal(t.cash_out),
        "balance": _opt_decimal(t.balance),
        "unit": t.unit,
        "category": t.category,
    }


def dict_to_rentqc_txn(d: Dict[str, Any]) -> RentQCTransaction:
    return RentQCTransaction(
        date=date.fromisoformat(d["date"]),
        payee=d["payee"],
        txn_type=d["txn_type"],
        reference=d.get("reference"),
        description=d["description"],
        cash_in=_from_opt_decimal(d.get("cash_in")),
        cash_out=_from_opt_decimal(d.get("cash_out")),
        balance=_from_opt_decimal(d.get("balance")),
        unit=d.get("unit"),
        category=d.get("category"),
    )


def rentqc_property_to_dict(p: RentQCProperty) -> Dict[str, Any]:
    return {
        "name": p.name,
        "beginning_balance": _opt_decimal(p.beginning_balance),
        "cash_in": _opt_decimal(p.cash_in),
        "cash_out": _opt_decimal(p.cash_out),
        "owner_disbursements": _opt_decimal(p.owner_disbursements),
        "ending_balance": _opt_decimal(p.ending_balance),
        "property_reserve": _opt_decimal(p.property_reserve),
        "prepayments": _opt_decimal(p.prepayments),
        "net_owner_funds": _opt_decimal(p.net_owner_funds),
        "total_cash_in_printed": _opt_decimal(p.total_cash_in_printed),
        "total_cash_out_printed": _opt_decimal(p.total_cash_out_printed),
        "transactions": [rentqc_txn_to_dict(t) for t in p.transactions],
    }


def dict_to_rentqc_property(d: Dict[str, Any]) -> RentQCProperty:
    prop = RentQCProperty(name=d["name"])
    prop.beginning_balance = _from_opt_decimal(d.get("beginning_balance"))
    prop.cash_in = _from_opt_decimal(d.get("cash_in"))
    prop.cash_out = _from_opt_decimal(d.get("cash_out"))
    prop.owner_disbursements = _from_opt_decimal(d.get("owner_disbursements"))
    prop.ending_balance = _from_opt_decimal(d.get("ending_balance"))
    prop.property_reserve = _from_opt_decimal(d.get("property_reserve"))
    prop.prepayments = _from_opt_decimal(d.get("prepayments"))
    prop.net_owner_funds = _from_opt_decimal(d.get("net_owner_funds"))
    prop.total_cash_in_printed = _from_opt_decimal(d.get("total_cash_in_printed"))
    prop.total_cash_out_printed = _from_opt_decimal(d.get("total_cash_out_printed"))
    prop.transactions = [dict_to_rentqc_txn(t) for t in d.get("transactions", [])]
    return prop


def rentqc_report_to_dict(r: RentQCReport) -> Dict[str, Any]:
    return {
        "source_path": str(r.source_path),
        "period_start": r.period_start.isoformat() if r.period_start else None,
        "period_end": r.period_end.isoformat() if r.period_end else None,
        "consolidated_beginning": _opt_decimal(r.consolidated_beginning),
        "consolidated_cash_in": _opt_decimal(r.consolidated_cash_in),
        "consolidated_cash_out": _opt_decimal(r.consolidated_cash_out),
        "consolidated_owner_disbursements": _opt_decimal(r.consolidated_owner_disbursements),
        "consolidated_ending": _opt_decimal(r.consolidated_ending),
        "properties": [rentqc_property_to_dict(p) for p in r.properties],
    }


def dict_to_rentqc_report(d: Dict[str, Any]) -> RentQCReport:
    report = RentQCReport(source_path=Path(d["source_path"]))
    report.period_start = date.fromisoformat(d["period_start"]) if d.get("period_start") else None
    report.period_end = date.fromisoformat(d["period_end"]) if d.get("period_end") else None
    report.consolidated_beginning = _from_opt_decimal(d.get("consolidated_beginning"))
    report.consolidated_cash_in = _from_opt_decimal(d.get("consolidated_cash_in"))
    report.consolidated_cash_out = _from_opt_decimal(d.get("consolidated_cash_out"))
    report.consolidated_owner_disbursements = _from_opt_decimal(d.get("consolidated_owner_disbursements"))
    report.consolidated_ending = _from_opt_decimal(d.get("consolidated_ending"))
    report.properties = [dict_to_rentqc_property(p) for p in d.get("properties", [])]
    return report


# =========================================================================
# Flat list helpers for Phase 2
# =========================================================================

def chase_txns_to_list(txns: Iterable[ChaseTransaction]) -> List[Dict[str, Any]]:
    return [chase_txn_to_dict(t) for t in txns]


def list_to_chase_txns(items: Iterable[Dict[str, Any]]) -> List[ChaseTransaction]:
    return [dict_to_chase_txn(d) for d in items]


def chase_credit_txns_to_list(txns: Iterable[ChaseCreditTransaction]) -> List[Dict[str, Any]]:
    return [chase_credit_txn_to_dict(t) for t in txns]


def list_to_chase_credit_txns(items: Iterable[Dict[str, Any]]) -> List[ChaseCreditTransaction]:
    return [dict_to_chase_credit_txn(d) for d in items]


def rentqc_reports_to_list(reports: Iterable[RentQCReport]) -> List[Dict[str, Any]]:
    return [rentqc_report_to_dict(r) for r in reports]


def list_to_rentqc_reports(items: Iterable[Dict[str, Any]]) -> List[RentQCReport]:
    return [dict_to_rentqc_report(d) for d in items]
