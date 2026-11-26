"""Имитационная модель коридора: заказы, рейсы, сравнение схем.

Параметры названы как в ANALYTICS.md (A01–A48), чтобы отчёт и API говорили
с одними и теми же именами. Все деньги — Decimal, округление в одном месте.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, replace
from decimal import Decimal

from .parameters import q

D = Decimal


@dataclass(frozen=True)
class Size:
    code: str
    um: int
    ops_factor: Decimal
    freight_factor: Decimal
    labor_minutes: int


SIZES = {
    "S": Size("S", 1, D("1.0"), D("1.0"), 3),
    "M": Size("M", 3, D("1.3"), D("1.5"), 4),
    "L": Size("L", 8, D("1.8"), D("2.5"), 6),
    "KGT": Size("KGT", 8, D("1.8"), D("2.5"), 6),
}
MESH_SIZES = ("S", "M")
MAX_DISTANCE_KM = 300


@dataclass(frozen=True)
class ModelParams:
    # --- допущения A01–A48 (ANALYTICS.md) ---
    hub_proc: Decimal = D("25")
    hub_leg_seller: Decimal = D("40")
    hub_last_mile: Decimal = D("35")
    hub_storage_rate: Decimal = D("3")
    hub_scale: Decimal = D("1")
    pvz_receive: Decimal = D("10")
    pvz_storage_rate: Decimal = D("3")
    pvz_assemble: Decimal = D("21")
    mesh_other: Decimal = D("10")
    pvz_fee_scale: Decimal = D("1")
    labor_rate_hour: Decimal = D("400")
    pvz_space_per_um_day: Decimal = D("1.667")
    storage_days: int = 3
    trip_km: Decimal = D("240")
    cost_per_km: Decimal = D("12")
    trip_hours: Decimal = D("6")
    driver_rate: Decimal = D("270")
    along_km: Decimal = D("40")
    along_hours: Decimal = D("1")
    trip_cost_scale: Decimal = D("1")
    vehicle_um: int = 300
    along_um: int = 60
    along_available: bool = True
    eta_hub_h: Decimal = D("48")
    eta_leg_h: Decimal = D("5")
    eta_shelf_h: Decimal = D("4")
    delta_t_h: Decimal = D("0")
    trip_days: tuple[int, ...] = (0, 2, 4, 5)  # 0 = понедельник, 4 рейса в неделю
    dep_hour: int = 8
    days: int = 28                         # 4 недели: 16 отправлений
    orders_per_day: float = 100.0
    nearby_share: float = 0.85
    share_S: float = 0.60
    share_M: float = 0.27
    share_L: float = 0.08
    share_KGT: float = 0.05
    shelf_hit_rate: float = 0.10
    pvz_count: int = 4
    pvz_capacity_um: Decimal = D("200")
    pvz_reserve: Decimal = D("0.15")
    trunk_stub: Decimal = D("120")
    fixed_cost_month: Decimal = D("60000")
    pvz_min_month: Decimal = D("5000")
    seller_unit_cost: Decimal = D("600")
    capital_rate_year: Decimal = D("0.2")
    seller_commission: Decimal = D("0.15")
    seller_logistics_fee: Decimal = D("60")
    return_rate: Decimal = D("0.05")
    # --- профиль спроса (внутренний, не входит в A-реестр) ---
    weekday_factor: float = 0.50           # пн–чт
    friday_factor: float = 1.35
    saturday_factor: float = 2.20
    sunday_factor: float = 1.60
    lanes: int = 1                          # один коридор ПВЗ → ПВЗ, как в отчёте
    peak_hours: tuple[float, ...] = (9, 10, 18, 19, 20)  # вечерний и утренний пик

    # --- производные стоимости (A-параметры × коэффициенты класса) ---
    def hub_cost(self, size_code: str) -> Decimal:
        size = SIZES[size_code]
        return q(
            (
                self.hub_proc * size.ops_factor
                + self.hub_storage_rate * size.um * self.storage_days
                + self.hub_leg_seller * size.freight_factor
                + self.hub_last_mile * size.freight_factor
            )
            * self.hub_scale
        )

    def mesh_var_cost(self, size_code: str) -> Decimal:
        size = SIZES[size_code]
        return q(
            (
                self.pvz_receive * size.ops_factor
                + self.pvz_storage_rate * size.um * self.storage_days
                + self.pvz_assemble * size.ops_factor
                + self.mesh_other * size.ops_factor
            )
            * self.pvz_fee_scale
        )

    def pvz_contribution(self, size_code: str) -> Decimal:
        size = SIZES[size_code]
        revenue = (
            self.pvz_receive * size.ops_factor
            + self.pvz_storage_rate * size.um * self.storage_days
            + self.pvz_assemble * size.ops_factor
        ) * self.pvz_fee_scale
        costs = (
            self.labor_rate_hour * D(size.labor_minutes) / D("60")
            + self.pvz_space_per_um_day * size.um * self.storage_days
        )
        return q(revenue - costs)

    def trip_cost(self, kind: str) -> Decimal:
        if kind == "ALONG":
            base = self.along_km * self.cost_per_km + self.along_hours * self.driver_rate
        else:
            base = self.trip_km * self.cost_per_km + self.trip_hours * self.driver_rate
        return q(base * self.trip_cost_scale)

    @property
    def corridors(self) -> int:
        return max(1, self.pvz_count // 2)

    def zone_lambda(self) -> float:
        return self.orders_per_day * self.nearby_share / self.corridors


def classify_zone(lambda_per_day: float) -> str:
    """Пороги плотности из бизнес-модели: GREEN ≥ 38, YELLOW 7–38, RED < 7."""
    if lambda_per_day >= 38:
        return "GREEN"
    if lambda_per_day >= 7:
        return "YELLOW"
    return "RED"


def _poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


@dataclass(frozen=True)
class SimOrder:
    t_h: float
    size: str
    near: bool
    shelf: bool


def generate_orders(params: ModelParams, seed: int) -> list[SimOrder]:
    rng = random.Random(seed)
    orders: list[SimOrder] = []
    weekend = (params.weekday_factor, params.friday_factor, params.saturday_factor, params.sunday_factor)
    for day in range(params.days):
        weekday = day % 7
        factor = weekend[0] if weekday <= 3 else weekend[weekday - 3]
        count = _poisson(rng, params.orders_per_day * factor)
        for _ in range(count):
            if rng.random() < 0.35 and params.peak_hours:
                hour = rng.choice(params.peak_hours) + rng.random()
            else:
                hour = rng.random() * 24
            t_h = day * 24 + hour
            roll = rng.random()
            if roll < params.share_S:
                size = "S"
            elif roll < params.share_S + params.share_M:
                size = "M"
            elif roll < params.share_S + params.share_M + params.share_L:
                size = "L"
            else:
                size = "KGT"
            near = rng.random() < params.nearby_share
            shelf = near and size in MESH_SIZES and rng.random() < params.shelf_hit_rate
            orders.append(SimOrder(t_h, size, near, shelf))
    orders.sort(key=lambda order: order.t_h)
    return orders


def _next_departure(params: ModelParams, t_h: float) -> float:
    """Ближайшее отправление 8:00 в день из trip_days (даже за горизонтом)."""
    day = int(math.floor(t_h / 24))
    for offset in range(0, 8):
        candidate_day = day + offset
        if candidate_day % 7 in params.trip_days:
            dep = candidate_day * 24 + params.dep_hour
            if dep > t_h + 0.5:
                return dep
    return (day + 7) * 24 + params.dep_hour


@dataclass
class RunResult:
    orders: int
    baseline_total: Decimal
    mesh_total: Decimal
    saving: Decimal
    funnel: dict[str, int]
    trips: dict[str, int]
    trip_cost_total: Decimal
    near_eta_sum: float
    near_orders: int
    mesh_orders: int
    pvz_contribution_total: Decimal
    capital_effect: Decimal

    @property
    def saving_pct(self) -> Decimal:
        return q(self.saving / self.baseline_total * 100) if self.baseline_total else D("0")


def simulate(params: ModelParams, seed: int = 42) -> RunResult:
    """Один прогон: одни и те же заказы через хаб и mesh."""
    orders = generate_orders(params, seed)
    zone = classify_zone(params.zone_lambda())
    baseline_total = D("0")
    mesh_total = D("0")
    mesh_orders = 0
    funnel = {"A": 0, "ALONG": 0, "DEDICATED": 0, "FAR": 0, "SIZE": 0, "TIME": 0, "TRIP": 0}
    trips = {"ALONG": 0, "DEDICATED": 0}
    trip_cost_total = D("0")
    near_eta_sum = 0.0
    near_orders = 0
    pvz_contrib_total = D("0")
    capital_effect = D("0")
    slots: dict[tuple[int, float], list[tuple[SimOrder, Decimal, Decimal]]] = {}

    for order in orders:
        size = SIZES[order.size]
        hub = params.hub_cost(order.size)
        baseline = hub + (params.trunk_stub if not order.near else D("0"))
        baseline_total += baseline
        mesh_var = params.mesh_var_cost(order.size)

        if order.near:
            near_orders += 1

        if not order.near:
            funnel["FAR"] += 1
            mesh_total += baseline
            near_eta_sum += 0
            continue

        if order.size not in MESH_SIZES:
            funnel["SIZE"] += 1
            mesh_total += baseline
            near_eta_sum += float(params.eta_hub_h)
            continue

        if order.shelf:
            funnel["A"] += 1
            mesh_orders += 1
            mesh_total += mesh_var
            near_eta_sum += float(params.eta_shelf_h)
            pvz_contrib_total += params.pvz_contribution(order.size)
            saved_days = (params.eta_hub_h - params.eta_shelf_h) / D("24")
            capital_effect += (
                params.seller_unit_cost * params.capital_rate_year * saved_days / D("365")
            )
            continue

        dep = _next_departure(params, order.t_h)
        wait = dep - order.t_h
        if wait + float(params.eta_leg_h) > float(params.eta_hub_h + params.delta_t_h):
            funnel["TIME"] += 1
            mesh_total += baseline
            near_eta_sum += float(params.eta_hub_h)
            continue
        lane_roll = (hash((order.t_h, order.size)) if False else 0)
        lane = int(order.t_h * 1000) % params.lanes
        slots.setdefault((lane, dep), []).append((order, mesh_var, hub))

    zone_allows_dedicated = zone == "GREEN"
    for (_lane, dep), queue in sorted(slots.items()):
        options: list[tuple[Decimal, list[tuple], str]] = []

        # вариант 1: только попутная загрузка
        along: list[tuple] = []
        if params.along_available:
            used = 0
            for item in queue:
                um = SIZES[item[0].size].um
                if used + um <= params.along_um:
                    along.append(item)
                    used += um
            if along:
                saving = sum((item[2] - item[1] for item in along), D("0"))
                options.append((saving - params.trip_cost("ALONG"), along, "ALONG"))

        # вариант 2: выделенный рейс
        if zone_allows_dedicated:
            dedicated: list[tuple] = []
            used = 0
            for item in queue:
                um = SIZES[item[0].size].um
                if used + um <= params.vehicle_um:
                    dedicated.append(item)
                    used += um
            if dedicated:
                saving = sum((item[2] - item[1] for item in dedicated), D("0"))
                options.append((saving - params.trip_cost("DEDICATED"), dedicated, "DEDICATED"))

            # вариант 3: попутный + выделенный на остаток
            if params.along_available and along:
                rest = [item for item in queue if item not in along]
                second: list[tuple] = []
                used = 0
                for item in rest:
                    um = SIZES[item[0].size].um
                    if used + um <= params.vehicle_um:
                        second.append(item)
                        used += um
                if second:
                    saving = sum((item[2] - item[1] for item in along + second), D("0"))
                    options.append(
                        (
                            saving - params.trip_cost("ALONG") - params.trip_cost("DEDICATED"),
                            along + second,
                            "BOTH",
                        )
                    )

        best_net = D("0")
        best_choice: list[tuple] = []
        best_kind = ""
        for net, items, kind in options:
            if net > best_net:
                best_net, best_choice, best_kind = net, items, kind

        if not best_choice:
            for order, mesh_var, hub in queue:
                funnel["TRIP"] += 1
                mesh_total += hub
                near_eta_sum += float(params.eta_hub_h)
            continue

        chosen_ids = {id(item) for item in best_choice}
        kinds = {"ALONG"} if best_kind == "ALONG" else {"DEDICATED"} if best_kind == "DEDICATED" else {"ALONG", "DEDICATED"}
        trip_cost = sum((params.trip_cost(kind) for kind in kinds), D("0"))
        trip_cost_total += trip_cost
        for kind in kinds:
            trips[kind] += 1
        per_order_cost = trip_cost / D(len(best_choice))
        for item in best_choice:
            order, mesh_var, hub = item
            funnel["ALONG" if best_kind == "ALONG" else "DEDICATED"] += 1
            mesh_orders += 1
            mesh_total += mesh_var + per_order_cost
            wait = dep - order.t_h
            near_eta_sum += wait + float(params.eta_leg_h)
            pvz_contrib_total += params.pvz_contribution(order.size)
            saved_days = (params.eta_hub_h - (D(str(wait)) + params.eta_leg_h)) / D("24")
            capital_effect += (
                params.seller_unit_cost * params.capital_rate_year * saved_days / D("365")
            )
        for item in queue:
            if id(item) in chosen_ids:
                continue
            order, mesh_var, hub = item
            funnel["TRIP"] += 1
            mesh_total += hub
            near_eta_sum += float(params.eta_hub_h)

    return RunResult(
        orders=len(orders),
        baseline_total=baseline_total,
        mesh_total=mesh_total,
        saving=q(baseline_total - mesh_total),
        funnel=funnel,
        trips=trips,
        trip_cost_total=trip_cost_total,
        near_eta_sum=near_eta_sum,
        near_orders=near_orders,
        mesh_orders=mesh_orders,
        pvz_contribution_total=pvz_contrib_total,
        capital_effect=capital_effect,
    )


def monthly(value: Decimal, params: ModelParams) -> Decimal:
    return q(value * D("30") / D(params.days))


def metrics(params: ModelParams, run: RunResult) -> dict[str, object]:
    """Показатели прогона в формате отчёта (₽/мес и доли)."""
    month_factor = D("30") / D(params.days)
    baseline_total = monthly(run.baseline_total, params)
    mesh_total = monthly(run.mesh_total, params)
    saving = q(baseline_total - mesh_total)
    contribution = monthly(run.pvz_contribution_total, params) / D(params.pvz_count)
    return {
        "orders": run.orders,
        "orders_per_day": q(D(run.orders) / D(params.days)),
        "cost_per_order_hub": q(run.baseline_total / D(run.orders)) if run.orders else D("0"),
        "cost_per_order_mesh": q(run.mesh_total / D(run.orders)) if run.orders else D("0"),
        "saving_month": saving,
        "saving_pct": q(saving / baseline_total * 100) if baseline_total else D("0"),
        "after_fixed_month": q(saving - params.fixed_cost_month),
        "mesh_share": q(D(run.mesh_orders) / D(run.orders) * 100) if run.orders else D("0"),
        "mesh_orders": run.mesh_orders,
        "near_eta_h": q(D(str(run.near_eta_sum)) / D(run.near_orders)) if run.near_orders else D("0"),
        "pvz_contribution_month": contribution,
        "capital_effect_month": monthly(run.capital_effect, params),
        "trips_along": run.trips["ALONG"],
        "trips_dedicated": run.trips["DEDICATED"],
        "funnel": {key: round(value * 100 / run.orders, 1) if run.orders else 0 for key, value in run.funnel.items()},
        "month_factor": month_factor,
    }


def run_avg(params: ModelParams, seeds: tuple[int, ...] = (1, 2, 3, 4, 5)) -> dict[str, object]:
    """Среднее по прогонам: убирает случайность одного месяца."""
    runs = [simulate(params, seed) for seed in seeds]
    count = D(len(runs))
    aggregated = {
        "orders": sum(run.orders for run in runs),
        "baseline_total": sum((run.baseline_total for run in runs), D("0")) / count,
        "mesh_total": sum((run.mesh_total for run in runs), D("0")) / count,
        "near_eta_sum": sum(run.near_eta_sum for run in runs) / len(runs),
        "near_orders": sum(run.near_orders for run in runs) / len(runs),
        "mesh_orders": sum(run.mesh_orders for run in runs) / len(runs),
        "pvz_contribution_total": sum((run.pvz_contribution_total for run in runs), D("0")) / count,
        "capital_effect": sum((run.capital_effect for run in runs), D("0")) / count,
        "trip_cost_total": sum((run.trip_cost_total for run in runs), D("0")) / count,
    }
    funnel = {key: sum(run.funnel[key] for run in runs) / len(runs) for key in runs[0].funnel}
    trips = {key: sum(run.trips[key] for run in runs) / len(runs) for key in runs[0].trips}
    combined = RunResult(
        orders=round(aggregated["orders"] / len(runs)),
        baseline_total=aggregated["baseline_total"],
        mesh_total=aggregated["mesh_total"],
        saving=q(aggregated["baseline_total"] - aggregated["mesh_total"]),
        funnel=funnel,
        trips=trips,
        trip_cost_total=aggregated["trip_cost_total"],
        near_eta_sum=aggregated["near_eta_sum"],
        near_orders=round(aggregated["near_orders"]),
        mesh_orders=round(aggregated["mesh_orders"]),
        pvz_contribution_total=aggregated["pvz_contribution_total"],
        capital_effect=aggregated["capital_effect"],
    )
    return metrics(params, combined)


def scenario_params(base: ModelParams, kind: str) -> ModelParams:
    if kind == "pessimistic":
        return replace(
            base,
            trip_cost_scale=D("1.25"),
            hub_scale=D("0.85"),
            orders_per_day=base.orders_per_day * 0.75,
            nearby_share=max(0.0, base.nearby_share - 0.10),
            pvz_fee_scale=D("1.15"),
            shelf_hit_rate=base.shelf_hit_rate / 2,
        )
    if kind == "optimistic":
        return replace(
            base,
            trip_cost_scale=D("0.75"),
            hub_scale=D("1.15"),
            orders_per_day=base.orders_per_day * 1.25,
            nearby_share=min(1.0, base.nearby_share + 0.10),
            pvz_fee_scale=D("0.85"),
            shelf_hit_rate=base.shelf_hit_rate * 2,
        )
    return base
