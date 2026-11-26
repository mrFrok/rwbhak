"""Ежедневные начисления хранения по модельным часам.

Хранение начисляется за каждый день, который проходит при `POST /time/advance`:
ПВЗ получает 3 ₽ × УМ × количество, продавец платит по прогрессивному тарифу
с 4-го дня. Ключ проводки включает партию и дату, поэтому повторный сдвиг
времени не задваивает начисления — это проверяется тестом.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from core import parameters as P
from core.parameters import q
from ..models import Batch, LedgerEntry

D = Decimal


def _seller_daily_rate(day_index: int) -> Decimal:
    """Тариф продавца за УМ-день: первые 3 дня бесплатно."""
    for end_day, rate in P.STORAGE_TIERS:
        if end_day is None or day_index <= end_day:
            return rate
    return P.STORAGE_TIERS[-1][1]


def _already_charged(db: Session, key: str) -> bool:
    return db.scalar(select(LedgerEntry.id).where(LedgerEntry.idempotency_key == key).limit(1)) is not None


def accrue_storage(db: Session, *, previous: datetime, current: datetime, at: datetime) -> int:
    """Провести хранение за дни между previous и current. Возвращает число дней."""
    if current <= previous:
        return 0
    batches = db.scalars(select(Batch).where(Batch.qty > 0)).all()
    charged_days = 0
    day = previous.date() + timedelta(days=1)
    while day <= current.date():
        for batch in batches:
            if batch.received_at.date() >= day:
                continue
            day_index = (day - batch.received_at.date()).days
            key = f"storage:{batch.id}:{day.isoformat()}"
            if _already_charged(db, key):
                continue
            size = P.get_size(batch.actual_class)
            units = batch.qty
            payout = q(P.MESH_STORAGE_PER_UM_DAY * size.um * units)
            fee = q(_seller_daily_rate(day_index) * size.um * units)
            if payout > 0:
                db.add(LedgerEntry(account="marketplace", order_id=None, entry_type="STORAGE_PVZ",
                                   amount_kop=-int(payout * 100), idempotency_key=key, line_no=0, created_at=at))
                db.add(LedgerEntry(account=f"pvz:{batch.pvz_id}", order_id=None, entry_type="STORAGE_PVZ",
                                   amount_kop=int(payout * 100), idempotency_key=key, line_no=1, created_at=at))
            if fee > 0:
                db.add(LedgerEntry(account=f"seller:{batch.sku.seller_id}", order_id=None, entry_type="STORAGE_SELLER",
                                   amount_kop=-int(fee * 100), idempotency_key=key, line_no=0, created_at=at))
                db.add(LedgerEntry(account="marketplace", order_id=None, entry_type="STORAGE_SELLER",
                                   amount_kop=int(fee * 100), idempotency_key=key, line_no=1, created_at=at))
        charged_days += 1
        day += timedelta(days=1)
    db.flush()
    _apply_removals(db, current=current, at=at)
    return charged_days


def _apply_removals(db: Session, *, current: datetime, at: datetime) -> None:
    """День 15+ без продаж: остаток вывозится на хаб, продавец платит 35 ₽/ед.

    Алерт `REMOVAL_D15` виден на 15-й день, а сам вывоз выполняется следующим
    сдвигом часов — как «ближайшим рейсом» в бизнес-модели.
    """
    batches = db.scalars(select(Batch).where(Batch.qty > 0)).all()
    for batch in batches:
        age_days = (current.date() - batch.received_at.date()).days
        if age_days <= P.REMOVAL_DAY or batch.qty_free <= 0:
            continue
        key = f"removal:{batch.id}"
        if _already_charged(db, key):
            continue
        amount = q(P.REMOVAL_FEE * batch.qty_free)
        db.add(LedgerEntry(account=f"seller:{batch.sku.seller_id}", order_id=None, entry_type="REMOVAL_FEE",
                           amount_kop=-int(amount * 100), idempotency_key=key, line_no=0, created_at=at))
        db.add(LedgerEntry(account="marketplace", order_id=None, entry_type="REMOVAL_FEE",
                           amount_kop=int(amount * 100), idempotency_key=key, line_no=1, created_at=at))
        batch.qty = 0
        batch.qty_free = 0
    db.flush()
