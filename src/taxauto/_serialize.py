"""JSON serialization helpers for intermediate caches.

Keeps per-year cached data interoperable between CLI steps without forcing
every module to know about pydantic or dataclass-wizard.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Dict, Iterable, List

from taxauto.categorize.mapper import TaggedTransaction
from taxauto.parsers.bank import Transaction
from taxauto.parsers.pm_ltr import PMEntry


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


def txns_to_list(txns: Iterable[Transaction]) -> List[Dict[str, Any]]:
    return [txn_to_dict(t) for t in txns]


def list_to_txns(items: Iterable[Dict[str, Any]]) -> List[Transaction]:
    return [dict_to_txn(d) for d in items]


def pm_list_to_list(entries: Iterable[PMEntry]) -> List[Dict[str, Any]]:
    return [pm_to_dict(e) for e in entries]


def list_to_pm_list(items: Iterable[Dict[str, Any]]) -> List[PMEntry]:
    return [dict_to_pm(d) for d in items]
