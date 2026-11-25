"""Справочники, допущения, модельные часы."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from core import parameters as P
from ..db import get_db
from ..models import Pvz, Seller, Sku
from ..schemas import TimeIn
from ..services import clock, idempotency

router = APIRouter(tags=["catalog"])


@router.get("/params")
def params() -> dict[str, object]:
    return {
        "assumptions": P.registry(),
        "mix": {"S": 0.70, "M": 0.30},
        "note": "Допущения команды, а не тарифы RWB. Меняются в core/parameters.py.",
    }


@router.get("/pvz")
def list_pvz(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    rows = db.scalars(select(Pvz).options(joinedload(Pvz.city)).order_by(Pvz.id)).all()
    return [
        {
            "id": pvz.id,
            "name": pvz.name,
            "address": pvz.address,
            "city": pvz.city.name,
            "city_id": pvz.city_id,
            "capacity_um": pvz.capacity_um,
            "available_um": pvz.available_um,
            "reserve_pct": pvz.reserve_pct,
            "quiet_windows": pvz.quiet_windows,
        }
        for pvz in rows
    ]


@router.get("/sellers")
def list_sellers(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    rows = db.scalars(select(Seller).order_by(Seller.id)).all()
    return [{"id": seller.id, "name": seller.name, "contact": seller.contact} for seller in rows]


@router.get("/skus")
def list_skus(seller_id: int | None = None, db: Session = Depends(get_db)) -> list[dict[str, object]]:
    query = select(Sku).options(joinedload(Sku.seller)).order_by(Sku.id)
    if seller_id is not None:
        query = query.where(Sku.seller_id == seller_id)
    return [
        {
            "id": sku.id,
            "name": sku.name,
            "seller_id": sku.seller_id,
            "seller": sku.seller.name,
            "size_class": sku.size_class,
            "um": sku.um,
            "price": sku.price_kop / 100,
            "unit_cost": sku.unit_cost_kop / 100,
            "special": sku.special,
        }
        for sku in db.scalars(query).all()
    ]


@router.get("/time")
def get_time(db: Session = Depends(get_db)) -> dict[str, object]:
    return {"now": clock.now(db).isoformat()}


@router.post("/time/advance")
def advance_time(
    body: TimeIn,
    db: Session = Depends(get_db),
    key: str = Depends(idempotency.require_key),
) -> dict[str, object]:
    if body.empty:
        raise HTTPException(400, "Нужно указать days или hours")
    fp = idempotency.fingerprint("POST", "/time/advance", body.model_dump())
    cached = idempotency.replay(db, key, fp)
    if cached is not None:
        return cached
    at = clock.now(db)
    new_time = clock.advance(db, days=body.days, hours=body.hours)
    result = {"now": new_time.isoformat(), "advanced_from": at.isoformat()}
    idempotency.remember(db, key, fp, "time_advanced", result, new_time)
    db.commit()
    return result
