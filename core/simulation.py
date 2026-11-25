"""Сравнение схем на одном потоке заказов. Без БД: одни и те же входные данные."""

from __future__ import annotations

import random
from dataclasses import dataclass
from decimal import Decimal

from . import parameters as P
from .economics import hub_cost, mesh_variable_cost, trip_cost
from .parameters import q


@dataclass(frozen=True)
class FlowOrder:
    size_class: str
    distance_km: int
    zone_class: str
    special: bool = False


def build_flow(count: int = P.DEMO_ORDERS, seed: int = P.SEED) -> list[FlowOrder]:
    """Синтетический поток: 70% S, 30% M, 15% дальних, редкие L и YELLOW."""
    rng = random.Random(seed)
    flow: list[FlowOrder] = []
    for _ in range(count):
        far = rng.random() < float(P.DEMO_FAR_SHARE)
        roll = rng.random()
        size = "S" if roll < 0.70 else "M"
        if not far and rng.random() < 0.04:
            size = "L"
        if far:
            distance = rng.randint(400, 1500)
            zone = P.ZONE_RED
        else:
            distance = rng.randint(20, 120)
            zone = P.ZONE_YELLOW if rng.random() < 0.25 else P.ZONE_GREEN
        flow.append(FlowOrder(size, distance, zone))
    return flow


def _eligible(order: FlowOrder, kind: str) -> bool:
    zone_ok = order.zone_class == P.ZONE_GREEN or (
        order.zone_class == P.ZONE_YELLOW and kind == P.TRIP_KIND_ALONG
    )
    return (
        order.distance_km <= P.MAX_MESH_DISTANCE_KM
        and zone_ok
        and order.size_class in P.MESH_SIZE_CODES
        and not order.special
    )


def plan_trips(orders: list[FlowOrder], kind: str = P.TRIP_KIND_DEDICATED) -> list[list[FlowOrder]]:
    """Жадно набиваем рейсы по вместимости в порядке потока."""
    trips: list[list[FlowOrder]] = []
    current: list[FlowOrder] = []
    used = 0
    for order in orders:
        if not _eligible(order, kind):
            continue
        um = P.get_size(order.size_class).um
        if used + um > P.TRIP_CAPACITY_UM:
            trips.append(current)
            current, used = [], 0
        current.append(order)
        used += um
    if current:
        trips.append(current)
    return trips


def compare(
    orders: list[FlowOrder] | None = None,
    kind: str = P.TRIP_KIND_DEDICATED,
    days: int = P.DEMO_DAYS,
    *,
    trip_factor: Decimal = Decimal("1"),
    hub_factor: Decimal = Decimal("1"),
    storage_factor: Decimal = Decimal("1"),
) -> dict[str, object]:
    flow = build_flow() if orders is None else orders
    if not flow or days < 1:
        raise ValueError("comparison requires orders and a positive duration")

    def baseline(order: FlowOrder) -> Decimal:
        return q(hub_cost(order.size_class) * hub_factor)

    def mesh(order: FlowOrder) -> Decimal:
        size = P.get_size(order.size_class)
        storage = P.MESH_STORAGE_PER_UM_DAY * size.um * P.MESH_STORAGE_DAYS
        bonus_factor = 1 + P.ON_TIME_BONUS_PCT
        return q(mesh_variable_cost(order.size_class) + storage * (storage_factor - 1) * bonus_factor)

    total = len(flow)
    hub_total = sum((baseline(order) for order in flow), Decimal("0"))
    route_cost = q(trip_cost(kind) * trip_factor)
    mesh_total = Decimal("0")
    mesh_orders = 0
    trips = plan_trips(flow, kind)
    accepted_trips = 0
    rejected_trips = 0
    for trip in trips:
        cost = route_cost + sum(mesh(order) for order in trip)
        hub_cost_trip = sum(baseline(order) for order in trip)
        if cost <= hub_cost_trip:
            accepted_trips += 1
            mesh_orders += len(trip)
            mesh_total += cost
        else:
            rejected_trips += 1
            mesh_total += hub_cost_trip

    hub_only = total - mesh_orders
    mesh_total += sum(baseline(order) for order in flow if not _eligible(order, kind))

    saving = hub_total - mesh_total
    per_day = Decimal(total) / Decimal(days)
    return {
        "flow_orders": total,
        "orders_per_day": q(per_day),
        "trip_kind": kind,
        "trip_cost": route_cost,
        "totals": {
            "hub_cost": q(hub_total),
            "mesh_cost": q(mesh_total),
            "saving": q(saving),
            "saving_pct": q(saving / hub_total * 100) if hub_total else Decimal("0"),
            "cost_per_order_hub": q(hub_total / total),
            "cost_per_order_mesh": q(mesh_total / total),
        },
        "mesh": {
            "orders": mesh_orders,
            "share_pct": q(Decimal(mesh_orders) / Decimal(total) * 100),
            "trips": accepted_trips,
        },
        "hub": {
            "orders": hub_only,
            "share_pct": q(Decimal(hub_only) / Decimal(total) * 100),
        },
        "rejected_trips": rejected_trips,
        "mix": {"S": 0.70, "M": 0.30, "far_share": float(P.DEMO_FAR_SHARE)},
    }


def sensitivity(flow: list[FlowOrder], kind: str, days: int) -> list[dict[str, object]]:
    """Меняем реальный параметр и заново отбираем рейсы на том же потоке."""
    parameters = {
        "Стоимость рейса": "trip_factor",
        "Себестоимость хаба": "hub_factor",
        "Хранение в ПВЗ": "storage_factor",
    }
    base = compare(flow, kind, days)
    base_cost = base["totals"]["cost_per_order_mesh"]
    result = []
    for name, key in parameters.items():
        for delta in (Decimal("-0.2"), Decimal("0.2")):
            scenario = compare(flow, kind, days, **{key: Decimal("1") + delta})
            cost = scenario["totals"]["cost_per_order_mesh"]
            result.append(
                {
                    "parameter": name,
                    "delta_pct": q(delta * 100),
                    "cost_per_order": q(cost),
                    "saving_vs_base_pct": q((cost - base_cost) / base_cost * 100),
                }
            )
    return result
