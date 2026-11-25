"""Рейсы: планирование, отправка, прибытие, сбой и перестроение."""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from core import ledger as L
from core import parameters as P
from core.economics import mesh_saving
from ..models import Order, Pvz, Trip
from ..money import from_kop, plain, rub, to_kop
from . import ledger_store
from .orders import _evaluate, find_zone


def trip_payload(trip: Trip, full: bool = False) -> dict[str, object]:
    data: dict[str, object] = {
        "id": trip.id,
        "status": trip.status,
        "kind": trip.kind,
        "from_pvz": {"id": trip.from_pvz.id, "name": trip.from_pvz.name},
        "to_pvz": {"id": trip.to_pvz.id, "name": trip.to_pvz.name},
        "departs_at": trip.departs_at.isoformat(),
        "cost": rub(trip.cost_kop),
        "capacity_um": trip.capacity_um,
        "used_um": trip.used_um,
        "free_um": trip.free_um,
        "orders": len([o for o in trip.orders if o.status != "CANCELLED"]),
    }
    if full:
        from .orders import order_payload

        data["order_list"] = [order_payload(o) for o in trip.orders]
    return data


def _get_trip(db: Session, trip_id: int) -> Trip:
    trip = db.scalar(
        select(Trip)
        .options(
            joinedload(Trip.from_pvz),
            joinedload(Trip.to_pvz),
            selectinload(Trip.orders).options(
                joinedload(Order.sku),
                joinedload(Order.seller),
                joinedload(Order.source_pvz),
                joinedload(Order.buyer_pvz),
                joinedload(Order.batch),
            ),
        )
        .where(Trip.id == trip_id)
    )
    if trip is None:
        raise HTTPException(404, "Рейс не найден")
    return trip


def plan(
    db: Session,
    *,
    from_pvz_id: int,
    to_pvz_id: int,
    kind: str,
    departs_at: datetime,
) -> dict[str, object]:
    source = db.get(Pvz, from_pvz_id)
    target = db.get(Pvz, to_pvz_id)
    if source is None or target is None:
        raise HTTPException(404, "ПВЗ рейса не найден")
    if source.id == target.id:
        raise HTTPException(409, "Пункты отправления и прибытия должны различаться")
    zone = find_zone(db, source.city_id, target.city_id)
    if zone is None or zone.class_ == P.ZONE_RED or zone.distance_km > P.MAX_MESH_DISTANCE_KM:
        raise HTTPException(
            409, "Для этих ПВЗ нет допустимого коридора mesh"
        )
    if zone.class_ == P.ZONE_YELLOW and kind != P.TRIP_KIND_ALONG:
        raise HTTPException(409, "В зоне YELLOW разрешены только попутные рейсы")
    trip = Trip(
        from_pvz_id=source.id,
        to_pvz_id=target.id,
        kind=kind,
        departs_at=departs_at,
        cost_kop=to_kop(P.TRIP_KIND_COST[kind]),
        capacity_um=P.TRIP_CAPACITY_UM,
        status="PLANNED",
    )
    db.add(trip)
    db.flush()
    db.refresh(trip)
    return trip_payload(trip)


def depart(db: Session, trip_id: int, key: str, at: datetime) -> dict[str, object]:
    trip = _get_trip(db, trip_id)
    if trip.status != "PLANNED":
        raise HTTPException(409, f"Рейс в статусе {trip.status} нельзя отправить")
    if not trip.orders:
        raise HTTPException(409, "Пустой рейс отправлять нельзя")
    if sum(mesh_saving(order.sku.size_class) for order in trip.orders) < from_kop(trip.cost_kop):
        raise HTTPException(409, "Рейс ещё не окупается: недостаточно заказов")
    # Сборка выполняется до отправки; явная ручная сборка также доступна.
    for order in trip.orders:
        if order.status == "RESERVED":
            ledger_store.post(
                db,
                L.picking(order.sku.size_class, order.source_pvz_id),
                f"{key}:pick:{order.id}",
                at,
                order.id,
            )
            order.status = "PICKED"
            order.picked_at = at
    trip.status = "IN_TRANSIT"
    for order in trip.orders:
        if order.status == "PICKED":
            order.status = "IN_TRIP"
    db.flush()
    return trip_payload(trip, full=True)


def arrive(db: Session, trip_id: int, at: datetime) -> dict[str, object]:
    trip = _get_trip(db, trip_id)
    if trip.status != "IN_TRANSIT":
        raise HTTPException(409, f"Рейс в статусе {trip.status} ещё не в пути")
    trip.status = "ARRIVED"
    for order in trip.orders:
        if order.status == "IN_TRIP":
            order.status = "ARRIVED"
    db.flush()
    return trip_payload(trip, full=True)


def fail(db: Session, trip_id: int, at: datetime) -> dict[str, object]:
    """Срыв рейса: пересчитать заказы на другой рейс или отправить в хаб."""
    trip = _get_trip(db, trip_id)
    if trip.status not in ("PLANNED", "IN_TRANSIT"):
        raise HTTPException(409, f"Рейс в статусе {trip.status} уже завершён")
    trip.status = "FAILED"
    affected = [o for o in trip.orders if o.status in ("RESERVED", "PICKED", "IN_TRIP")]
    moved = 0
    failed_to_hub = 0
    # Снимаем старые брони места перед тем, как проверить новый рейс.
    for order in affected:
        order.trip = None
        order.mode = "C"
        order.status = "ROUTED_HUB"
    db.flush()
    for order in affected:
        remaining = order.eta_hub_h - (at - order.created_at).total_seconds() / 3600
        target, decision = _evaluate(
            db, order.sku, order.source_pvz, order.buyer_pvz, order.batch, at,
            max_eta_h=remaining,
        )
        order.eta_mesh_h = decision["eta_mesh_h"]
        order.cost_mesh_kop = to_kop(decision["cost_mesh"])
        if target is not None and decision["mode"] == "B":
            order.trip = target
            order.mode = "B"
            order.status = "PICKED" if order.picked_at else "RESERVED"
            order.decision_json = plain(decision)
            moved += 1
        else:
            order.decision_json = {
                **plain(decision),
                "blocked_by": ["trip_failed", *decision["blocked_by"]],
                "reason": "Рейс сорван: заказ переведён в схему через хаб",
            }
            failed_to_hub += 1
        db.flush()
    payload = trip_payload(trip, full=True)
    payload["rerouted"] = {"to_other_trip": moved, "to_hub": failed_to_hub}
    return payload
