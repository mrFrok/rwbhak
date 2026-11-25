"""Приёмка, заказ, сборка, выдача, возврат. Здесь живут границы транзакций."""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from core import ledger as L
from core import parameters as P
from core.solver import OrderRequest, TripLoad, decide
from ..models import Batch, Order, Pvz, Sku, Trip, Zone
from ..money import plain, rub, to_kop
from . import ledger_store


def find_zone(db: Session, city_a: int, city_b: int) -> Zone | None:
    return db.scalar(
        select(Zone).where(
            ((Zone.from_city_id == city_a) & (Zone.to_city_id == city_b))
            | ((Zone.from_city_id == city_b) & (Zone.to_city_id == city_a))
        )
    )


def pvz_space(db: Session, pvz_id: int) -> int:
    """Свободное место под новый товар: доступная ёмкость минус занятое."""
    pvz = db.get(Pvz, pvz_id)
    used, incoming = _space_usage(db, pvz_id)
    return max(0, pvz.available_um - used - incoming)


def _space_usage(db: Session, pvz_id: int) -> tuple[int, int]:
    rows = db.execute(
        select(Batch, Sku).join(Sku, Batch.sku_id == Sku.id).where(Batch.pvz_id == pvz_id)
    ).all()
    used = sum(batch.qty * sku.um for batch, sku in rows)
    incoming = sum(db.scalars(select(Order.um).where(
        Order.buyer_pvz_id == pvz_id,
        Order.mode == "B",
        Order.status.in_(("RESERVED", "PICKED", "IN_TRIP", "ARRIVED")),
    )))
    return used, incoming


def pvz_stock(db: Session, pvz_id: int) -> dict[str, object]:
    pvz = db.get(Pvz, pvz_id)
    if pvz is None:
        raise HTTPException(404, "ПВЗ не найден")
    rows = db.execute(
        select(Batch, Sku).join(Sku, Batch.sku_id == Sku.id).where(Batch.pvz_id == pvz_id)
    ).all()
    stock_units = sum(batch.qty_free for batch, _ in rows)
    used_um, incoming_um = _space_usage(db, pvz_id)
    free_um = max(0, pvz.available_um - used_um - incoming_um)
    return {
        "pvz": {
            "id": pvz.id,
            "name": pvz.name,
            "address": pvz.address,
            "city": pvz.city.name,
            "capacity_um": pvz.capacity_um,
            "available_um": pvz.available_um,
            "quiet_windows": pvz.quiet_windows,
        },
        "units": stock_units,
        "free_um": free_um,
        "used_um": used_um,
        "incoming_um": incoming_um,
        "load_pct": round((used_um + incoming_um) / pvz.capacity_um * 100, 1) if pvz.capacity_um else 0,
        "space_free_um": free_um,
        "batches": [
            {
                "id": batch.id,
                "sku_id": sku.id,
                "sku": sku.name,
                "size_class": sku.size_class,
                "um": sku.um,
                "qty": batch.qty,
                "qty_free": batch.qty_free,
                "received_at": batch.received_at.isoformat(),
                "declared_class": batch.declared_class,
                "actual_class": batch.actual_class,
            }
            for batch, sku in rows
        ],
    }


def _pick_batch(
    db: Session,
    sku: Sku,
    buyer: Pvz,
    source_pvz_id: int | None,
    batch_id: int | None,
) -> Batch:
    query = (
        select(Batch)
        .options(joinedload(Batch.pvz), joinedload(Batch.sku))
        .where(Batch.sku_id == sku.id, Batch.qty_free > 0)
        .with_for_update(of=Batch)
    )
    if batch_id is not None:
        query = query.where(Batch.id == batch_id)
    if source_pvz_id is not None:
        query = query.where(Batch.pvz_id == source_pvz_id)
    batches = list(db.scalars(query).all())
    if not batches:
        raise HTTPException(409, "Нет свободного остатка этого SKU в выбранных ПВЗ")

    def rank(batch: Batch) -> tuple[int, datetime]:
        same_pvz = 0 if batch.pvz_id == buyer.id else 1
        same_city = 0 if batch.pvz.city_id == buyer.city_id else 1
        return (same_pvz * 10 + same_city, batch.received_at)

    return sorted(batches, key=rank)[0]


def _trips_for(db: Session, source: Pvz, buyer: Pvz) -> list[Trip]:
    trips = db.scalars(
        select(Trip)
        .options(
            selectinload(Trip.orders).selectinload(Order.sku),
            joinedload(Trip.from_pvz),
            joinedload(Trip.to_pvz),
        )
        .where(Trip.status == "PLANNED")
        .order_by(Trip.departs_at)
    ).all()
    return [
        trip
        for trip in trips
        if trip.from_pvz_id == source.id and trip.to_pvz_id == buyer.id
    ]


def _evaluate(
    db: Session,
    sku: Sku,
    source: Pvz,
    buyer: Pvz,
    batch: Batch,
    at: datetime,
    *,
    max_eta_h: float | None = None,
) -> tuple[Trip | None, dict[str, object]]:
    zone = find_zone(db, source.city_id, buyer.city_id)
    same_city = source.city_id == buyer.city_id
    distance = zone.distance_km if zone else (0 if same_city else 9999)
    zone_class = zone.class_ if zone else P.ZONE_RED
    space = pvz_space(db, buyer.id)
    trips = sorted(
        _trips_for(db, source, buyer),
        key=lambda trip: (0 if trip.from_pvz_id == source.id else 1, trip.departs_at),
    )

    last_decision: dict[str, object] | None = None
    for trip in trips:
        if trip.departs_at < at:
            continue
        wait_hours = (trip.departs_at - at).total_seconds() / 3600
        if max_eta_h is not None and wait_hours + P.MESH_ETA_OVERHEAD_H > max_eta_h:
            continue
        load = TripLoad(
            kind=trip.kind,
            free_um=trip.free_um,
            existing_sizes=tuple(
                order.sku.size_class for order in trip.orders if order.status != "CANCELLED"
            ),
            wait_hours=wait_hours,
        )
        decision = decide(
            OrderRequest(
                size_class=sku.size_class,
                special=sku.special,
                distance_km=distance,
                zone_class=zone_class,
                same_pvz_stock=batch.qty_free if source.id == buyer.id else 0,
                buyer_free_um=space,
                trip=load,
            )
        )
        last_decision = decision
        if decision["mode"] in ("A", "B"):
            return (trip if decision["mode"] == "B" else None), decision

    if last_decision is not None:
        return None, last_decision
    return None, decide(
        OrderRequest(
            size_class=sku.size_class,
            special=sku.special,
            distance_km=distance,
            zone_class=zone_class,
            same_pvz_stock=batch.qty_free if source.id == buyer.id else 0,
            buyer_free_um=space,
            trip=None,
        )
    )


def order_payload(order: Order) -> dict[str, object]:
    saving = rub(order.cost_hub_kop - order.cost_mesh_kop) if order.mode in ("A", "B") else 0
    return {
        "id": order.id,
        "status": order.status,
        "mode": order.mode,
        "sku": {
            "id": order.sku_id,
            "name": order.sku.name,
            "size_class": order.sku.size_class,
            "price": rub(order.sku.price_kop),
            "seller_id": order.seller_id,
            "seller": order.seller.name,
        },
        "source_pvz": {"id": order.source_pvz.id, "name": order.source_pvz.name},
        "buyer_pvz": {"id": order.buyer_pvz.id, "name": order.buyer_pvz.name},
        "trip_id": order.trip_id,
        "eta_mesh_h": order.eta_mesh_h,
        "eta_hub_h": order.eta_hub_h,
        "cost_mesh": rub(order.cost_mesh_kop),
        "cost_hub": rub(order.cost_hub_kop),
        "saving": saving,
        "decision": order.decision_json,
        "created_at": order.created_at.isoformat(),
        "picked_at": order.picked_at.isoformat() if order.picked_at else None,
        "issued_at": order.issued_at.isoformat() if order.issued_at else None,
    }


def create_order(
    db: Session,
    *,
    sku_id: int,
    buyer_pvz_id: int,
    source_pvz_id: int | None,
    batch_id: int | None,
    key: str,
    at: datetime,
) -> dict[str, object]:
    sku = db.get(Sku, sku_id)
    if sku is None:
        raise HTTPException(404, "SKU не найден")
    buyer = db.get(Pvz, buyer_pvz_id)
    if buyer is None:
        raise HTTPException(404, "ПВЗ покупателя не найден")

    batch = _pick_batch(db, sku, buyer, source_pvz_id, batch_id)
    source = batch.pvz
    trip, decision = _evaluate(db, sku, source, buyer, batch, at)
    mode = str(decision["mode"])

    batch.qty_free -= 1
    order = Order(
        sku_id=sku.id,
        batch_id=batch.id,
        seller_id=sku.seller_id,
        source_pvz_id=source.id,
        buyer_pvz_id=buyer.id,
        trip_id=trip.id if mode == "B" and trip is not None else None,
        um=sku.um,
        status="ROUTED_HUB" if mode == "C" else "RESERVED",
        mode=mode,
        eta_mesh_h=decision["eta_mesh_h"],
        eta_hub_h=decision["eta_hub_h"],
        cost_mesh_kop=to_kop(decision["cost_mesh"]),
        cost_hub_kop=to_kop(decision["cost_hub"]),
        decision_json=plain(decision),
        created_at=at,
    )
    db.add(order)
    db.flush()
    db.refresh(order)
    return order_payload(order)


def _get_order(db: Session, order_id: int) -> Order:
    order = db.scalar(
        select(Order)
        .options(
            joinedload(Order.sku),
            joinedload(Order.seller),
            joinedload(Order.source_pvz),
            joinedload(Order.buyer_pvz),
            joinedload(Order.batch),
        )
        .where(Order.id == order_id)
    )
    if order is None:
        raise HTTPException(404, "Заказ не найден")
    return order


def pick(db: Session, order_id: int, key: str, at: datetime) -> dict[str, object]:
    order = _get_order(db, order_id)
    if order.status != "RESERVED":
        raise HTTPException(409, f"Сборка недоступна в статусе {order.status}")
    ledger_store.post(
        db, L.picking(order.sku.size_class, order.source_pvz_id), key, at, order.id
    )
    order.status = "PICKED"
    order.picked_at = at
    db.flush()
    return order_payload(order)


def issue(db: Session, order_id: int, key: str, at: datetime) -> dict[str, object]:
    order = _get_order(db, order_id)
    allowed = {
        "A": ("RESERVED", "PICKED"),
        "B": ("ARRIVED",),
        "C": ("ROUTED_HUB", "PICKED"),
    }[order.mode]
    if order.status not in allowed:
        raise HTTPException(409, f"Выдача недоступна в статусе {order.status}")

    days = max(0, (at - order.batch.received_at).days)
    size = order.sku.size_class
    entries = L.storage(size, order.source_pvz_id, order.seller_id, days)
    is_on_time = (at - order.created_at).total_seconds() / 3600 <= order.eta_hub_h
    if order.mode == "A" or is_on_time:
        entries += L.issue(size, order.source_pvz_id, order.mode, days)
    if order.mode == "C":
        entries += L.hub_route(size)
    ledger_store.post(db, entries, key, at, order.id)
    order.batch.qty -= 1
    if order.batch.qty_free > order.batch.qty:
        order.batch.qty_free = order.batch.qty
    order.status = "ISSUED"
    order.issued_at = at
    db.flush()
    return order_payload(order)


def return_request(db: Session, order_id: int, at: datetime) -> dict[str, object]:
    order = _get_order(db, order_id)
    if order.status != "ISSUED":
        raise HTTPException(409, "Возврат возможен только для выданного заказа")
    order.status = "RETURN_REQUESTED"
    order.returned_at = at
    db.flush()
    return order_payload(order)


def return_transit(db: Session, order_id: int, at: datetime) -> dict[str, object]:
    order = _get_order(db, order_id)
    if order.status != "RETURN_REQUESTED":
        raise HTTPException(409, f"Возврат в пути недоступен в статусе {order.status}")
    order.status = "RETURN_IN_TRANSIT"
    db.flush()
    return order_payload(order)


def return_accept(db: Session, order_id: int, key: str, at: datetime) -> dict[str, object]:
    """Завершение возврата (бизнес-модель v0.3, раздел 12.2).

    Товар остаётся в ПВЗ выдачи, если этот SKU там востребован и есть место;
    иначе возвращается в партию отправителя (в MVP вывоз на хаб не моделируется).
    Бонус за выдачу сторнируется, продавец платит обратную логистику 50 ₽.
    """
    order = _get_order(db, order_id)
    if order.status != "RETURN_IN_TRANSIT":
        raise HTTPException(409, f"Принять возврат в статусе {order.status} нельзя")
    entries = L.return_event(
        order.sku.size_class,
        order.source_pvz_id,
        order.seller_id,
        reverse_picking=order.picked_at is not None,
        reverse_bonus=order.mode in ("A", "B"),
    )
    ledger_store.post(db, entries, key, at, order.id)
    order.status = "RETURNED"

    batch = _restock_batch(db, order)
    batch.qty_free += 1
    db.flush()
    return order_payload(order)


def _restock_batch(db: Session, order: Order) -> Batch:
    """Партия для возврата в сток: своя полка ПВЗ выдачи или партия отправителя.

    Партия, из которой заказ был выдан, уже потеряла единицу безвозвратно
    (`qty -= 1` при выдаче), поэтому для пополнения ищем другую живую партию.
    """
    if order.buyer_pvz_id != order.source_pvz_id and pvz_space(db, order.buyer_pvz_id) >= order.sku.um:
        candidate = db.scalar(
            select(Batch)
            .where(
                Batch.pvz_id == order.buyer_pvz_id,
                Batch.sku_id == order.sku_id,
                Batch.qty_free < Batch.qty,
            )
            .order_by(Batch.received_at)
        )
        if candidate is not None and candidate.id != order.batch.id:
            return candidate
    live = db.scalar(
        select(Batch)
        .where(Batch.sku_id == order.sku_id, Batch.qty_free < Batch.qty)
        .order_by(Batch.received_at)
    )
    return live if live is not None else order.batch
