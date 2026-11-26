"""Решатель маршрута: режимы A / B / C с объяснением по фильтрам."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from . import parameters as P
from .economics import (
    baseline_cost,
    mesh_saving,
    mesh_variable_cost,
    trip_cost,
    trip_cost_per_order,
)


@dataclass(frozen=True)
class TripLoad:
    """Что уже известно о рейсе на момент решения."""

    kind: str
    free_um: int
    existing_sizes: tuple[str, ...] = ()
    wait_hours: float = 24.0

    @property
    def orders(self) -> int:
        return len(self.existing_sizes)

    @property
    def saved_so_far(self) -> Decimal:
        return sum((mesh_saving(code) for code in self.existing_sizes), Decimal("0"))


@dataclass(frozen=True)
class OrderRequest:
    size_class: str
    special: bool = False
    distance_km: int = P.TRIP_DISTANCE_KM
    zone_class: str = P.ZONE_GREEN
    same_pvz_stock: int = 0
    buyer_free_um: int = P.PVZ_CAPACITY_UM
    trip: TripLoad | None = None
    buyer_price_mesh: Decimal = Decimal("0")
    buyer_price_hub: Decimal = Decimal("0")


@dataclass
class FilterResult:
    code: str
    title: str
    ok: bool
    actual: str
    limit: str

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "title": self.title,
            "ok": self.ok,
            "actual": self.actual,
            "limit": self.limit,
        }


def _filter(code: str, title: str, ok: bool, actual: object, limit: object) -> FilterResult:
    return FilterResult(code, title, bool(ok), str(actual), str(limit))


def decide(req: OrderRequest) -> dict[str, object]:
    """Вернуть режим, оценки и полный список фильтров."""
    size = P.get_size(req.size_class)
    distance_ok = req.distance_km <= P.MAX_MESH_DISTANCE_KM
    hub = baseline_cost(req.size_class, distant=not distance_ok)
    eta_hub = P.HUB_ETA_H

    # Режим A: товар уже лежит в ПВЗ покупателя.
    shelf_ok = req.same_pvz_stock > 0 and size.mesh_allowed and not req.special
    shelf_filter = _filter(
        "shelf", "Товар на полке ПВЗ покупателя", shelf_ok,
        f"в наличии {req.same_pvz_stock} шт", "> 0",
    )
    if shelf_ok:
        cost = mesh_variable_cost(req.size_class, shelf_sale=True)
        return {
            "mode": "A",
            "eta_mesh_h": P.MESH_ETA_SHELF_H,
            "eta_hub_h": eta_hub,
            "cost_mesh": cost,
            "cost_hub": hub,
            "saving": hub - cost,
            "trip_orders": 0,
            "filters": [shelf_filter.as_dict()],
            "reason": "Товар уже в ПВЗ покупателя: выдача с полки без перевозки",
            "blocked_by": [],
        }

    trip = req.trip
    zone_ok = req.zone_class == P.ZONE_GREEN or (
        req.zone_class == P.ZONE_YELLOW and trip is not None and trip.kind == P.TRIP_KIND_ALONG
    )
    size_ok = size.mesh_allowed and not req.special
    if trip is None:
        space_ok = req.buyer_free_um >= size.um
        space_actual = f"в ПВЗ {req.buyer_free_um} УМ, рейс не назначен"
    else:
        space_ok = req.buyer_free_um >= size.um and trip.free_um >= size.um
        space_actual = f"в ПВЗ {req.buyer_free_um} УМ, в рейсе {trip.free_um} УМ"
    eta_mesh = (trip.wait_hours + P.MESH_ETA_OVERHEAD_H) if trip else None
    time_ok = eta_mesh is not None and eta_mesh <= eta_hub + P.DELTA_T_H
    price_ok = req.buyer_price_mesh <= req.buyer_price_hub
    trip_needed = trip_cost(trip.kind) if trip else Decimal("0")
    saved_total = (trip.saved_so_far if trip else Decimal("0")) + mesh_saving(req.size_class)
    trip_ok = trip is not None and saved_total >= trip_needed

    if trip is not None:
        n_after = trip.orders + 1
        cost_mesh = mesh_variable_cost(req.size_class) + trip_cost_per_order(trip.kind, n_after)
        trip_actual = f"экономия {saved_total:.2f} ₽ на {n_after} заказах"
        trip_limit = f">= {trip_needed:.2f} ₽"
    else:
        n_after = 0
        cost_mesh = mesh_variable_cost(req.size_class)
        trip_actual = "нет запланированного рейса по этому коридору"
        trip_limit = "нужен рейс ПВЗ → ПВЗ"

    filters = [
        _filter("distance", "Расстояние до 300 км", distance_ok,
                f"{req.distance_km} км", f"<= {P.MAX_MESH_DISTANCE_KM} км"),
        _filter("zone", "Плотность зоны", zone_ok,
                req.zone_class if trip is None else f"{req.zone_class}, рейс {trip.kind}",
                "GREEN или YELLOW+ALONG"),
        _filter("size", "Габарит допускается в mesh", size_ok,
                f"{req.size_class}{' / особый' if req.special else ''}", "S или M, не особый"),
        _filter("space", "Есть свободное место", space_ok, space_actual, f">= {size.um} УМ"),
        _filter("time", "Срок не хуже хаба", time_ok,
                f"{eta_mesh:.0f} ч" if eta_mesh is not None else "нет рейса",
                f"<= {eta_hub} ч"),
        _filter("price", "Цена покупателя не растёт", price_ok,
                f"{req.buyer_price_mesh} <= {req.buyer_price_hub}", "mesh не дороже"),
        _filter("trip", "Рейс окупается", trip_ok, trip_actual, trip_limit),
    ]

    blocked = [f.code for f in filters if not f.ok]
    mode = "B" if not blocked else "C"
    reason = (
        f"Все фильтры пройдены: рейс {trip.kind}, {n_after} заказов, экономия {saved_total:.2f} ₽"
        if mode == "B"
        else "Не пройден фильтр: " + ", ".join(blocked)
    )

    return {
        "mode": mode,
        "eta_mesh_h": eta_mesh,
        "eta_hub_h": eta_hub,
        "cost_mesh": cost_mesh,
        "cost_hub": hub,
        "saving": hub - cost_mesh if mode == "B" else Decimal("0"),
        "trip_orders": n_after,
        "filters": [f.as_dict() for f in filters],
        "reason": reason,
        "blocked_by": blocked,
    }
