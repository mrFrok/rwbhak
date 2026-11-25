"""Аналитика ПВЗ и продавца из ledger и заказов. Не хранится отдельно."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from core import parameters as P
from core.economics import pvz_contribution, seller_margin
from core.parameters import q
from ..models import LedgerEntry, Order, Pvz, Seller
from ..money import from_kop, rub
from . import ledger_store
from .orders import pvz_stock


def _labor(size_code: str):
    size = P.get_size(size_code)
    return q(P.PVZ_LABOR_COST_HOUR * size.labor_minutes / 60), size.overhead


def pvz_analytics(db: Session, pvz_id: int) -> dict[str, object]:
    pvz = db.get(Pvz, pvz_id)
    if pvz is None:
        raise HTTPException(404, "ПВЗ не найден")
    account = f"pvz:{pvz_id}"
    entries = ledger_store.by_account(db, account)

    revenue_kop = sum(entry.amount_kop for entry in entries)
    by_type: dict[str, int] = defaultdict(int)
    by_day: dict[str, int] = defaultdict(int)
    for entry in entries:
        by_type[entry.entry_type] += entry.amount_kop
        by_day[entry.created_at.date().isoformat()] += entry.amount_kop

    orders = db.scalars(
        select(Order)
        .options(joinedload(Order.sku), joinedload(Order.batch))
        .where(Order.source_pvz_id == pvz_id)
    ).all()
    labor_kop = 0
    overhead_kop = 0
    units = 0
    for order in orders:
        if order.status in ("CREATED", "CANCELLED"):
            continue
        labor, overhead = _labor(order.sku.size_class)
        labor_kop += int(labor * 100)
        overhead_kop += int(overhead * 100)
        units += 1

    contribution_kop = revenue_kop - labor_kop - overhead_kop
    um_days = sum(
        order.sku.um
        * max(1, ((order.issued_at or order.created_at) - order.batch.received_at).days)
        for order in orders
    )
    return {
        "pvz": {"id": pvz.id, "name": pvz.name, "city": pvz.city.name},
        "revenue": rub(revenue_kop),
        "revenue_by_type": {k: rub(v) for k, v in sorted(by_type.items())},
        "labor": rub(labor_kop),
        "overhead": rub(overhead_kop),
        "contribution": rub(contribution_kop),
        "units": units,
        "contribution_per_um_day": rub(contribution_kop) / um_days if um_days else 0.0,
        "days": [{"date": day, "revenue": rub(value)} for day, value in sorted(by_day.items())],
        "ledger": [
            {
                "id": entry.id,
                "account": entry.account,
                "type": entry.entry_type,
                "amount": rub(entry.amount_kop),
                "order_id": entry.order_id,
                "created_at": entry.created_at.isoformat(),
            }
            for entry in entries[-50:]
        ],
        "stock": pvz_stock(db, pvz_id),
        "note": "Вклад = выручка ПВЗ по ledger − труд − расходники. Бонусы входят в выручку.",
    }


def seller_analytics(db: Session, seller_id: int, at: datetime) -> dict[str, object]:
    seller = db.get(Seller, seller_id)
    if seller is None:
        raise HTTPException(404, "Продавец не найден")
    orders = db.scalars(
        select(Order)
        .options(joinedload(Order.sku), joinedload(Order.batch), joinedload(Order.buyer_pvz))
        .where(Order.seller_id == seller_id)
        .order_by(Order.created_at)
    ).all()

    items = []
    totals = {
        "price": Decimal("0"), "margin": Decimal("0"), "commission": Decimal("0"),
        "storage": Decimal("0"), "returns": Decimal("0"),
    }
    for order in orders:
        if order.status in ("CREATED", "CANCELLED"):
            continue
        end = order.issued_at or at
        days = max(0, (end - order.batch.received_at).days)
        price = from_kop(order.sku.price_kop)
        unit_cost = from_kop(order.sku.unit_cost_kop)
        breakdown = seller_margin(order.sku.size_class, price, unit_cost, days)
        items.append(
            {
                "order_id": order.id,
                "sku": order.sku.name,
                "size_class": order.sku.size_class,
                "status": order.status,
                "mode": order.mode,
                "created_at": order.created_at.isoformat(),
                "storage_days": days,
                **{key: float(value) for key, value in breakdown.items()},
                "margin_pct": float(q(breakdown["margin"] / price * 100)) if price else 0.0,
            }
        )
        for key in totals:
            totals[key] += breakdown[key]

    revenue = totals.pop("price")
    return {
        "seller": {"id": seller.id, "name": seller.name},
        "totals": {key: float(value) for key, value in totals.items()}
        | {"price": float(revenue), "margin_pct": float(q(totals["margin"] / revenue * 100)) if revenue else 0.0},
        "orders": items[-100:],
        "note": (
            "Полная юнит-экономика продавца по бизнес-модели v0.3: комиссия 15%, "
            "эквайринг 1,5%, логистика 65/95 ₽, обратная логистика 50 ₽ при отказе, "
            "налог УСН 6% с выручки. Все ставки — допущения команды."
        ),
    }
