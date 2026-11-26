"""Приёмка партий и остатки ПВЗ."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from core import ledger as L
from core import parameters as P
from ..db import get_db
from ..errors import DomainError
from ..models import Batch, Order, Pvz, Sku
from ..schemas import BatchIn
from ..services import clock, idempotency, intake, ledger_store
from ..services.orders import pvz_space, pvz_stock

router = APIRouter(tags=["stock"])


@router.post("/batches", status_code=201)
def receive_batch(
    body: BatchIn,
    db: Session = Depends(get_db),
    key: str = Depends(idempotency.require_key),
) -> dict[str, object]:
    fp = idempotency.fingerprint("POST", "/batches", body.model_dump())
    cached = idempotency.replay(db, key, fp)
    if cached is not None:
        return cached

    sku = db.get(Sku, body.sku_id)
    pvz = db.get(Pvz, body.pvz_id)
    if sku is None:
        raise HTTPException(404, "SKU не найден")
    if pvz is None:
        raise HTTPException(404, "ПВЗ не найден")
    if body.seller_id is not None and body.seller_id != sku.seller_id:
        raise DomainError(400, "SELLER_MISMATCH", "SKU не принадлежит указанному продавцу")
    if body.declared_class not in {*P.SIZE_CLASSES, P.SPECIAL_SIZE}:
        raise HTTPException(422, "Неизвестный класс габарита")
    actual = body.actual_class or body.declared_class
    if actual == P.SPECIAL_SIZE or body.declared_class == P.SPECIAL_SIZE or sku.special:
        raise DomainError(409, "SIZE_NOT_ALLOWED", "Этот товар не допускается к хранению в ПВЗ")
    if actual not in P.SIZE_CLASSES:
        raise HTTPException(422, "Неизвестный фактический класс габарита")
    size = P.get_size(actual)
    if not size.mesh_allowed:
        raise DomainError(409, "SIZE_NOT_ALLOWED", "Этот товар не допускается к хранению в ПВЗ")

    at = clock.now(db)
    result = intake.receive(
        db,
        sku=sku,
        target=pvz,
        qty=body.qty,
        declared_class=body.declared_class,
        actual=actual,
        distribute=body.distribute,
        key=key,
        at=at,
    )
    idempotency.remember(db, key, fp, "batch_received", result, at)
    db.commit()
    return result


@router.get("/pvz/{pvz_id}/stock")
def stock(pvz_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    return pvz_stock(db, pvz_id)


@router.get("/pvz/{pvz_id}/batches")
def batches(pvz_id: int, db: Session = Depends(get_db)) -> list[dict[str, object]]:
    rows = db.scalars(
        select(Batch)
        .options(joinedload(Batch.sku))
        .where(Batch.pvz_id == pvz_id)
        .order_by(Batch.received_at)
    ).all()
    return [
        {
            "id": batch.id,
            "sku": batch.sku.name,
            "size_class": batch.sku.size_class,
            "qty": batch.qty,
            "qty_free": batch.qty_free,
            "received_at": batch.received_at.isoformat(),
        }
        for batch in rows
    ]


@router.get("/pvz/{pvz_id}/alerts")
def alerts(pvz_id: int, db: Session = Depends(get_db)) -> list[dict[str, object]]:
    """Алерты неликвида считаются от модельных часов, а не хранятся."""
    now_value = clock.now(db)
    rows = db.scalars(
        select(Batch).options(joinedload(Batch.sku)).where(Batch.pvz_id == pvz_id)
    ).all()
    result: list[dict[str, object]] = []
    for batch in rows:
        if batch.qty_free == 0:
            continue
        age = (now_value - batch.received_at).days
        sold = db.scalar(select(Order.id).where(
            Order.batch_id == batch.id, Order.issued_at.is_not(None),
        ).limit(1))
        if age >= P.REMOVAL_DAY:
            result.append(
                {
                    "batch_id": batch.id,
                    "type": "REMOVAL_D15",
                    "sku": batch.sku.name,
                    "age_days": age,
                    "note": "Требуется вывоз, пополнение заблокировано",
                }
            )
        elif age >= P.NO_SALES_ALERT_DAY and sold is None:
            result.append(
                {
                    "batch_id": batch.id,
                    "type": "NO_SALES_D7",
                    "sku": batch.sku.name,
                    "age_days": age,
                    "note": "Нет продаж: остановить пополнение по SKU",
                }
            )
    return result
