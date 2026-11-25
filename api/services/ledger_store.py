"""Запись проводок ядра в ledger."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.ledger import Entry
from ..models import LedgerEntry
from ..money import to_kop


def post(
    db: Session,
    entries: list[Entry],
    key: str,
    at: datetime,
    order_id: int | None = None,
) -> None:
    for entry in entries:
        db.add(
            LedgerEntry(
                account=entry.account,
                order_id=order_id,
                entry_type=entry.kind,
                amount_kop=to_kop(entry.amount),
                idempotency_key=key,
                line_no=entry.line_no,
                created_at=at,
            )
        )
    db.flush()


def by_account(db: Session, account: str) -> list[LedgerEntry]:
    return list(
        db.scalars(
            select(LedgerEntry)
            .where(LedgerEntry.account == account)
            .order_by(LedgerEntry.created_at, LedgerEntry.id)
        ).all()
    )


def account_total(db: Session, account: str) -> int:
    value = db.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount_kop), 0)).where(
            LedgerEntry.account == account
        )
    )
    return int(value or 0)
