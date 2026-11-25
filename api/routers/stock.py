"""Приёмка партий и остатки ПВЗ."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from core import ledger as L
from core import parameters as P
from ..db import get_db
from ..models import Batch, Order, Pvz, Sku
from ..schemas import BatchIn
from ..services import clock, idempotency, ledger_store
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
    if body.declared_class not in {*P.SIZE_CLASSES, P.SPECIAL_SIZE}:
        raise HTTPException(422, "Неизвестный класс габарита")
    actual = body.actual_class or body.declared_class
    if actual not in P.SIZE_CLASSES:
        raise HTTPException(422, "Неизвестный фактический класс габарита")
    # Бизнес-модель v0.3: пересчёт класса при расхождении; L — отказ в mesh.
    if actual == "L" and actual != body.declared_class:
        raise HTTPException(
            409,
            "Фактический класс L: товар не допускается к хранению в ПВЗ, только через хаб",
        )
    if not P.get_size(actual).mesh_allowed or sku.special:
        raise HTTPException(409, "Этот товар не допускается к хранению в ПВЗ")

    at = clock.now(db)
    candidates = db.scalars(select(Batch).where(
        Batch.pvz_id == pvz.id, Batch.sku_id == sku.id, Batch.qty_free > 0,
    )).all()
    for candidate in candidates:
        age = (at - candidate.received_at).days
        sold = db.scalar(select(Order.id).where(
            Order.batch_id == candidate.id, Order.issued_at.is_not(None),
        ).limit(1))
        if age >= P.REMOVAL_DAY or (age >= P.NO_SALES_ALERT_DAY and sold is None):
            raise HTTPException(409, "Пополнение заблокировано: есть залежавшийся остаток этого SKU")

    need_um = sku.um * body.qty
    if need_um > pvz_space(db, pvz.id):
        raise HTTPException(
            409,
            f"Не хватает места: нужно {need_um} УМ, свободно {pvz_space(db, pvz.id)} УМ",
        )

    if sku.size_class == "M":
        medium_qty = sum(db.scalars(select(Batch.qty).join(Sku).where(
            Batch.pvz_id == pvz.id, Sku.size_class == "M",
        )))
        if medium_qty * sku.um + need_um > pvz.available_um * P.PVZ_M_UM_SHARE_LIMIT:
            raise HTTPException(409, "Превышен лимит места под товары класса M")
    batch = Batch(
        sku_id=sku.id,
        pvz_id=pvz.id,
        qty=body.qty,
        qty_free=body.qty,
        received_at=at,
        declared_class=body.declared_class,
        actual_class=actual,
    )
    db.add(batch)
    db.flush()
    # Тариф приёмки считаем по фактическому классу (пересчёт S → M по v0.3).
    entries = L.acceptance(actual, pvz.id, body.qty)
    ledger_store.post(db, entries, key, at)

    result = {
        "id": batch.id,
        "sku_id": sku.id,
        "pvz_id": pvz.id,
        "qty": batch.qty,
        "qty_free": batch.qty_free,
        "received_at": batch.received_at.isoformat(),
        "size_class": sku.size_class,
        "declared_class": batch.declared_class,
        "actual_class": batch.actual_class,
        "um_total": need_um,
        "acceptance_payout": float(entries[1].amount),
        "space_free_after_um": pvz_space(db, pvz.id),
    }
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
