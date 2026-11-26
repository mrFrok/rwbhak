"""Прогноз спроса по SKU и рекомендации по размещению.

Простая и объяснимая модель: средние продажи за окно истории, прогноз на
горизонт покрытия, вычитаем остаток и заказы в пути, ограничиваем свободным
местом и квотой M. Никакого «чёрного ящика» — каждая цифра в ответе.
"""

from __future__ import annotations

from datetime import timedelta
from math import ceil

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core import parameters as P
from ..errors import DomainError
from ..models import Batch, City, Order, Pvz, SellerCity, Sku, Zone
from ..services import clock
from ..services.orders import pvz_space

ACTIVE_ORDER_STATUSES = ("RESERVED", "PICKED", "IN_TRIP", "ARRIVED")


def _seller_city(db: Session, seller_id: int) -> City | None:
    return db.scalar(
        select(City).join(SellerCity, SellerCity.city_id == City.id).where(SellerCity.seller_id == seller_id)
    )


def _reachable_cities(db: Session, city_id: int | None) -> set[int]:
    """Город продавца и соседние города коридора ≤300 км (кроме RED)."""
    if city_id is None:
        return set()
    cities = {city_id}
    for zone in db.scalars(select(Zone).where(Zone.class_ != P.ZONE_RED)).all():
        if zone.distance_km > P.MAX_MESH_DISTANCE_KM:
            continue
        if zone.from_city_id == city_id:
            cities.add(zone.to_city_id)
        elif zone.to_city_id == city_id:
            cities.add(zone.from_city_id)
    return cities


def _medium_free_um(db: Session, pvz: Pvz) -> int:
    medium_qty = sum(
        db.scalars(select(Batch.qty).where(Batch.pvz_id == pvz.id, Batch.actual_class == "M"))
    )
    limit_um = int(pvz.available_um * P.PVZ_M_UM_SHARE_LIMIT)
    return max(0, limit_um - medium_qty * 3)


def _demand(db: Session, pvz_id: int, since) -> dict[int, int]:
    rows = db.execute(
        select(Order.sku_id, func.count(Order.id))
        .where(
            Order.buyer_pvz_id == pvz_id,
            Order.created_at >= since,
            Order.mode.in_(("A", "B")),  # дальние заказы идут через хаб и не создают локальный спрос
        )
        .group_by(Order.sku_id)
    ).all()
    return {sku_id: int(count) for sku_id, count in rows}


def _stock(db: Session, pvz_id: int) -> dict[int, int]:
    rows = db.execute(
        select(Batch.sku_id, func.coalesce(func.sum(Batch.qty_free), 0))
        .where(Batch.pvz_id == pvz_id)
        .group_by(Batch.sku_id)
    ).all()
    return {sku_id: int(qty) for sku_id, qty in rows}


def _incoming(db: Session, pvz_id: int) -> dict[int, int]:
    rows = db.execute(
        select(Order.sku_id, func.count(Order.id))
        .where(
            Order.buyer_pvz_id == pvz_id,
            Order.mode == "B",
            Order.status.in_(ACTIVE_ORDER_STATUSES),
        )
        .group_by(Order.sku_id)
    ).all()
    return {sku_id: int(count) for sku_id, count in rows}


def pvz_forecast(
    db: Session, pvz_id: int, *, window_days: int = 30, coverage_days: int = 3,
) -> dict[str, object]:
    pvz = db.get(Pvz, pvz_id)
    if pvz is None:
        raise DomainError(404, "NOT_FOUND", "ПВЗ не найден")
    at = clock.now(db)
    since = at - timedelta(days=window_days)
    demand = _demand(db, pvz_id, since)
    stock = _stock(db, pvz_id)
    incoming = _incoming(db, pvz_id)
    free_um = pvz_space(db, pvz_id)
    medium_free = _medium_free_um(db, pvz)

    pvz_reachable = _reachable_cities(db, pvz.city_id)
    items = []
    for sku_id, sold in demand.items():
        sku = db.get(Sku, sku_id)
        if sku is None:
            continue
        size = P.get_size(sku.size_class)
        if not size.mesh_allowed or sku.special:
            continue
        seller_city = _seller_city(db, sku.seller_id)
        reachable = seller_city is not None and seller_city.id in pvz_reachable
        avg_daily = sold / window_days
        target = ceil(avg_daily * coverage_days)
        have = stock.get(sku_id, 0)
        on_way = incoming.get(sku_id, 0)
        need = max(0, target - have - on_way)
        available_um = free_um
        if sku.size_class == "M":
            available_um = min(available_um, medium_free)
        recommended = min(need, available_um // size.um) if reachable else 0
        if recommended > 0:
            free_um -= recommended * size.um
            if sku.size_class == "M":
                medium_free -= recommended * size.um
        items.append(
            {
                "sku_id": sku.id,
                "sku": sku.name,
                "seller_id": sku.seller_id,
                "size_class": sku.size_class,
                "um": size.um,
                "sold": sold,
                "mean_daily": round(avg_daily, 2),
                "forecast_units": target,
                "stock": have,
                "incoming": on_way,
                "recommended": recommended,
                "recommended_um": recommended * size.um,
                "seller_city": seller_city.name if seller_city else None,
                "reachable": reachable,
                "reason": (
                    f"продано {sold} за {window_days} дн → прогноз {target} шт; "
                    f"на полке {have}, в пути {on_way}; продавец: "
                    f"{seller_city.name if seller_city else 'город не указан'}"
                    + ("" if reachable else " — прямой завоз невозможен, только хаб")
                ),
            }
        )

    items.sort(key=lambda row: (row["sold"], row["recommended"]), reverse=True)
    return {
        "pvz_id": pvz.id,
        "pvz_name": pvz.name,
        "window_days": window_days,
        "coverage_days": coverage_days,
        "free_um": pvz_space(db, pvz_id),
        "items": items[:30],
        "note": (
            "Прогноз = средние продажи за окно истории × дни покрытия. "
            "Рекомендация учитывает остаток, заказы в пути, свободное место и квоту M."
        ),
    }


def seller_recommendations(
    db: Session, seller_id: int, sku_id: int, *, window_days: int = 30, limit: int = 3,
) -> dict[str, object]:
    sku = db.get(Sku, sku_id)
    if sku is None:
        raise DomainError(404, "NOT_FOUND", "SKU не найден")
    if sku.seller_id != seller_id:
        raise DomainError(404, "NOT_FOUND", "SKU не принадлежит продавцу")
    at = clock.now(db)
    since = at - timedelta(days=window_days)
    seller_city = _seller_city(db, seller_id)
    allowed_cities = _reachable_cities(db, seller_city.id) if seller_city else set()

    scores = []
    for pvz in db.scalars(select(Pvz).order_by(Pvz.id)):
        if allowed_cities and pvz.city_id not in allowed_cities:
            continue
        demand = db.scalar(
            select(func.count(Order.id)).where(
                Order.buyer_pvz_id == pvz.id, Order.sku_id == sku_id, Order.created_at >= since
            )
        ) or 0
        stock = db.scalar(
            select(func.coalesce(func.sum(Batch.qty_free), 0)).where(
                Batch.pvz_id == pvz.id, Batch.sku_id == sku_id
            )
        ) or 0
        free = pvz_space(db, pvz.id)
        score = float(demand) * 10 + min(float(free), 50.0) * 0.5 - float(stock) * 4
        scores.append(
            {
                "pvz_id": pvz.id,
                "pvz_name": pvz.name,
                "city": pvz.city.name,
                "demand": int(demand),
                "stock": int(stock),
                "free_um": free,
                "score": round(score, 1),
            }
        )
    scores.sort(key=lambda row: row["score"], reverse=True)
    top = scores[:limit]
    if top:
        top[0]["hint"] = "лучший баланс спроса и свободного места"
    return {
        "seller_id": seller_id,
        "sku_id": sku_id,
        "sku": sku.name,
        "seller_city": seller_city.name if seller_city else None,
        "items": top,
        "note": (
            "Балл = спрос × 10 + свободное место × 0.5 − остаток × 4. "
            "Показаны только ПВЗ в городе продавца и коридоре до 300 км."
            if seller_city
            else "Город продавца не указан: показаны все ПВЗ, проверьте географию вручную."
        ),
    }
