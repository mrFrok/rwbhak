"""Приёмка партии с частичным размещением и распределением по другим ПВЗ."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from core import ledger as L
from core import parameters as P
from ..errors import DomainError
from ..models import Batch, Order, Pvz, Sku, Zone
from ..services import ledger_store
from ..services.orders import pvz_space


def _intake_blocked(db: Session, pvz_id: int, sku_id: int, at: datetime) -> bool:
    """Пополнение SKU в точку запрещено, если там залежался остаток."""
    candidates = db.scalars(
        select(Batch).where(Batch.pvz_id == pvz_id, Batch.sku_id == sku_id, Batch.qty_free > 0)
    ).all()
    for batch in candidates:
        age = (at - batch.received_at).days
        sold = db.scalar(
            select(Order.id)
            .where(Order.batch_id == batch.id, Order.issued_at.is_not(None))
            .limit(1)
        )
        if age >= P.REMOVAL_DAY or (age >= P.NO_SALES_ALERT_DAY and sold is None):
            return True
    return False


def _medium_free_um(db: Session, pvz: Pvz, unit_um: int) -> int:
    medium_qty = sum(
        db.scalars(
            select(Batch.qty).where(Batch.pvz_id == pvz.id, Batch.actual_class == "M")
        )
    )
    limit_um = int(pvz.available_um * P.PVZ_M_UM_SHARE_LIMIT)
    return max(0, limit_um - medium_qty * unit_um)


def _capacity_for(db: Session, pvz: Pvz, actual: str) -> int:
    """Сколько единиц этого класса влезет в ПВЗ с учётом квоты M."""
    free_um = pvz_space(db, pvz.id)
    if actual == "M":
        free_um = min(free_um, _medium_free_um(db, pvz, P.get_size(actual).um))
    return free_um // P.get_size(actual).um


def _destinations(db: Session, target: Pvz) -> list[Pvz]:
    """Целевой ПВЗ, затем точки того же города, затем города-коридоры до 300 км."""
    same_city = db.scalars(
        select(Pvz).where(Pvz.city_id == target.city_id, Pvz.id != target.id).order_by(Pvz.id)
    ).all()
    zones = db.scalars(select(Zone).where(Zone.class_ != P.ZONE_RED)).all()
    reachable_cities: set[int] = set()
    for zone in zones:
        if zone.distance_km > P.MAX_MESH_DISTANCE_KM:
            continue
        if zone.from_city_id == target.city_id:
            reachable_cities.add(zone.to_city_id)
        elif zone.to_city_id == target.city_id:
            reachable_cities.add(zone.from_city_id)
    reachable_cities.discard(target.city_id)
    corridor = db.scalars(
        select(Pvz).where(Pvz.city_id.in_(reachable_cities)).order_by(Pvz.city_id, Pvz.id)
    ).all()
    return [target, *same_city, *corridor]


def receive(
    db: Session,
    *,
    sku: Sku,
    target: Pvz,
    qty: int,
    declared_class: str,
    actual: str,
    distribute: bool,
    key: str,
    at: datetime,
) -> dict[str, object]:
    """Принять партию. При distribute=true остаток раскладывается по другим ПВЗ."""
    size = P.get_size(actual)
    remaining = qty
    allocations: list[dict[str, object]] = []
    destinations = _destinations(db, target) if distribute else [target]

    for pvz in destinations:
        if remaining <= 0:
            break
        if _intake_blocked(db, pvz.id, sku.id, at):
            if not distribute or pvz.id == target.id:
                raise DomainError(
                    409, "REPLENISHMENT_BLOCKED",
                    "Пополнение заблокировано: есть залежавшийся остаток этого SKU",
                    pvz_id=pvz.id,
                )
            continue
        capacity = _capacity_for(db, pvz, actual)
        if not distribute and capacity < qty:
            raise DomainError(
                409, "CAPACITY",
                f"Не хватает места: нужно {qty * size.um} УМ, свободно {capacity * size.um} УМ",
                free_um=capacity * size.um, needed_um=qty * size.um,
            )
        take = min(remaining, capacity)
        if take <= 0:
            continue
        batch = Batch(
            sku_id=sku.id,
            pvz_id=pvz.id,
            qty=take,
            qty_free=take,
            received_at=at,
            declared_class=declared_class,
            actual_class=actual,
        )
        db.add(batch)
        db.flush()
        entries = L.acceptance(actual, pvz.id, take)
        ledger_store.post(db, entries, f"{key}:pvz:{pvz.id}", at)
        allocations.append(
            {
                "pvz_id": pvz.id,
                "pvz_name": pvz.name,
                "city": pvz.city.name,
                "batch_id": batch.id,
                "qty": take,
                "um": take * size.um,
                "acceptance_payout": float(sum(entry.amount for entry in entries if entry.amount > 0)),
                "space_free_after_um": pvz_space(db, pvz.id),
            }
        )
        remaining -= take

    if not allocations:
        raise DomainError(
            409, "CAPACITY",
            f"Не хватает места: нужно {qty * size.um} УМ, свободно 0 УМ",
            free_um=0, needed_um=qty * size.um,
        )

    accepted = qty - remaining
    total_payout = sum(float(item["acceptance_payout"]) for item in allocations)
    return {
        "id": allocations[0]["batch_id"],
        "sku_id": sku.id,
        "pvz_id": allocations[0]["pvz_id"],
        "qty": accepted,
        "qty_free": accepted,
        "received_at": at.isoformat(),
        "size_class": actual,
        "declared_class": declared_class,
        "actual_class": actual,
        "um_total": accepted * size.um,
        "acceptance_payout": total_payout,
        "space_free_after_um": allocations[0]["space_free_after_um"],
        "partial": remaining > 0,
        "accepted_qty": accepted,
        "unplaced_qty": remaining,
        "distributed": len(allocations) > 1,
        "allocations": allocations,
    }
