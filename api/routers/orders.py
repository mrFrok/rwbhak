"""Заказы и их жизненный цикл."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from ..db import get_db
from ..models import LedgerEntry, Order
from ..money import rub
from ..schemas import OrderIn
from ..services import clock, idempotency
from ..services import orders as service
from ..services.orders import order_payload

router = APIRouter(tags=["orders"])


def _mutation(db: Session, path: str, body: dict, key: str, fn) -> dict[str, object]:
    fp = idempotency.fingerprint("POST", path, body)
    cached = idempotency.replay(db, key, fp)
    if cached is not None:
        return cached
    at = clock.now(db)
    result = fn(at)
    idempotency.remember(db, key, fp, path.strip("/").replace("/", "_"), result, at)
    db.commit()
    return result


@router.post("/orders", status_code=201)
def create_order(
    body: OrderIn,
    db: Session = Depends(get_db),
    key: str = Depends(idempotency.require_key),
) -> dict[str, object]:
    return _mutation(
        db,
        "/orders",
        body.model_dump(),
        key,
        lambda at: service.create_order(
            db,
            sku_id=body.sku_id,
            buyer_pvz_id=body.buyer_pvz_id,
            source_pvz_id=body.source_pvz_id,
            batch_id=body.batch_id,
            key=key,
            at=at,
        ),
    )


@router.get("/orders")
def list_orders(
    pvz_id: int | None = None,
    seller_id: int | None = None,
    status: str | None = None,
    mode: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    query = (
        select(Order)
        .options(
            joinedload(Order.sku),
            joinedload(Order.seller),
            joinedload(Order.source_pvz),
            joinedload(Order.buyer_pvz),
        )
        .order_by(Order.created_at.desc(), Order.id.desc())
        .limit(min(limit, 500))
    )
    if pvz_id is not None:
        query = query.where(or_(Order.source_pvz_id == pvz_id, Order.buyer_pvz_id == pvz_id))
    if seller_id is not None:
        query = query.where(Order.seller_id == seller_id)
    if status is not None:
        query = query.where(Order.status == status)
    if mode is not None:
        query = query.where(Order.mode == mode)
    return [order_payload(order) for order in db.scalars(query).all()]


@router.get("/orders/{order_id}")
def get_order(order_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    return order_payload(service._get_order(db, order_id))


@router.post("/orders/{order_id}/pick")
def pick(
    order_id: int,
    db: Session = Depends(get_db),
    key: str = Depends(idempotency.require_key),
) -> dict[str, object]:
    return _mutation(
        db, f"/orders/{order_id}/pick", {}, key, lambda at: service.pick(db, order_id, key, at)
    )


@router.post("/orders/{order_id}/issue")
def issue(
    order_id: int,
    db: Session = Depends(get_db),
    key: str = Depends(idempotency.require_key),
) -> dict[str, object]:
    return _mutation(
        db, f"/orders/{order_id}/issue", {}, key, lambda at: service.issue(db, order_id, key, at)
    )


@router.post("/orders/{order_id}/return")
def return_request(
    order_id: int,
    db: Session = Depends(get_db),
    key: str = Depends(idempotency.require_key),
) -> dict[str, object]:
    return _mutation(
        db, f"/orders/{order_id}/return", {}, key, lambda at: service.return_request(db, order_id, at)
    )


@router.post("/orders/{order_id}/return/transit")
def return_transit(
    order_id: int,
    db: Session = Depends(get_db),
    key: str = Depends(idempotency.require_key),
) -> dict[str, object]:
    return _mutation(
        db,
        f"/orders/{order_id}/return/transit",
        {},
        key,
        lambda at: service.return_transit(db, order_id, at),
    )


@router.post("/orders/{order_id}/return/accept")
def return_accept(
    order_id: int,
    db: Session = Depends(get_db),
    key: str = Depends(idempotency.require_key),
) -> dict[str, object]:
    return _mutation(
        db,
        f"/orders/{order_id}/return/accept",
        {},
        key,
        lambda at: service.return_accept(db, order_id, key, at),
    )


@router.get("/orders/{order_id}/ledger")
def order_ledger(order_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    order = service._get_order(db, order_id)
    entries = db.scalars(
        select(LedgerEntry).where(LedgerEntry.order_id == order_id).order_by(LedgerEntry.id)
    ).all()
    total = sum(entry.amount_kop for entry in entries)
    if total != 0 and order.status in ("ISSUED", "RETURNED"):
        raise HTTPException(500, "Проводки по заказу не сходятся в ноль")
    return {
        "order_id": order_id,
        "balance": rub(total),
        "entries": [
            {
                "id": entry.id,
                "account": entry.account,
                "type": entry.entry_type,
                "amount": rub(entry.amount_kop),
                "line_no": entry.line_no,
                "created_at": entry.created_at.isoformat(),
            }
            for entry in entries
        ],
    }
