"""Симуляция двух схем (хаб и mesh) на одном наборе синтетических заказов.

Правило решения для каждого заказа — те же четыре фильтра, что в бизнес-модели:
плотность района, габариты, срок, стоимость рейса. Возвращает метрики и «воронку»
причин, по которым заказ ушёл в хаб.
"""
import bisect
import math
import random
from collections import Counter
from dataclasses import dataclass

from .parameters import Params, UM, MESH_ELIGIBLE
from . import economics as E

WEEKDAY = (1.0, 1.0, 1.0, 1.0, 1.1, 1.3, 1.2)   # пн..вс, относительная нагрузка


@dataclass
class Order:
    id: int
    t: float          # часы от начала периода
    size: str
    nearby: bool


def _poisson(rng: random.Random, lam: float) -> int:
    limit, k, prod = math.exp(-lam), 0, 1.0
    while True:
        k += 1
        prod *= rng.random()
        if prod <= limit:
            return k - 1


def generate_orders(p: Params, seed: int = 42) -> list[Order]:
    """Синтетические заказы. Персональных данных нет, seed фиксирует воспроизводимость."""
    rng = random.Random(seed)
    mean_f = sum(WEEKDAY) / 7
    sizes = ["S", "M", "L", "KGT"]
    weights = [p.share_S, p.share_M, p.share_L, p.share_KGT]
    out: list[Order] = []
    for d in range(p.days):
        n = _poisson(rng, p.orders_per_day * WEEKDAY[d % 7] / mean_f)
        for _ in range(n):
            out.append(Order(0, d * 24 + 8 + rng.random() * 14,
                             rng.choices(sizes, weights)[0],
                             rng.random() < p.nearby_share))
    out.sort(key=lambda o: o.t)
    for i, o in enumerate(out):
        o.id = i
    return out


def departures(p: Params, horizon_h: float) -> list[float]:
    return [d * 24 + p.dep_hour for d in range(int(horizon_h // 24) + 1)
            if d % 7 in p.trip_days and d * 24 + p.dep_hour <= horizon_h]


def classify_zone(p: Params, lam: float, avg_saving: float) -> str:
    interval = 7 / len(p.trip_days)
    if avg_saving <= 0:
        return "RED"
    green = E.breakeven_orders(p, avg_saving) / interval
    yellow = E.breakeven_orders(p, avg_saving, along=True) / interval
    if lam >= green:
        return "GREEN"
    if lam >= yellow and p.along_available:
        return "YELLOW"
    return "RED"


def simulate(p: Params, seed: int = 42, dedicated_allowed: bool = True) -> dict:
    rng = random.Random(seed + 1000)
    horizon = p.days * 24
    deps_all = departures(p, horizon + 24 * 14)
    t_end = [d for d in deps_all if d <= horizon][-1]
    orders = [o for o in generate_orders(p, seed) if o.t <= t_end]
    days_eff = t_end / 24

    funnel: Counter = Counter()
    mode: dict[int, str] = {}       # id -> A / B_DED / B_ALONG / HUB
    eta: dict[int, float] = {}
    trips: list[dict] = []

    cand = []
    for o in orders:
        if not o.nearby:
            funnel["distance"] += 1
        elif o.size not in MESH_ELIGIBLE:
            funnel["size"] += 1
        elif E.saving(p, o.size) <= 0:
            funnel["unprofitable"] += 1
        else:
            cand.append(o)

    avg_sav = sum(E.saving(p, o.size) for o in cand) / len(cand) if cand else 0.0
    lam = len(cand) / days_eff
    zone = classify_zone(p, lam, avg_sav) if (dedicated_allowed or p.along_available) else "RED"
    if not dedicated_allowed and zone == "GREEN":
        zone = "YELLOW"

    if zone == "RED":
        funnel["zone"] += len(cand)
        accepted = []
        cap_factor = 1.0
    else:
        stock_um = sum(UM[o.size] for o in cand) / days_eff * p.storage_days
        cap_factor = min(1.0, p.pvz_avail_um_total / stock_um) if stock_um else 1.0
        accepted = []
        for o in cand:
            if rng.random() < cap_factor:
                accepted.append(o)
            else:
                funnel["capacity"] += 1

    b_cand = []
    for o in accepted:
        if rng.random() < p.shelf_hit_rate:
            mode[o.id], eta[o.id] = "A", p.eta_shelf_h
        else:
            b_cand.append(o)

    groups: dict[float, list[Order]] = {}
    for o in b_cand:
        d = deps_all[bisect.bisect_left(deps_all, o.t)]
        e = (d - o.t) + p.eta_leg_h
        if e <= p.eta_hub_h + p.delta_t_h:
            groups.setdefault(d, []).append(o)
            eta[o.id] = e
        else:
            funnel["time"] += 1

    for d, grp in sorted(groups.items()):
        # перебираем варианты рейса и берём лучший по чистой экономии
        ordered = sorted(grp, key=lambda o: -E.saving(p, o.size) / UM[o.size])
        along_set, um_acc = [], 0.0
        if p.along_available:
            for o in ordered:
                if um_acc + UM[o.size] <= p.along_um:
                    along_set.append(o)
                    um_acc += UM[o.size]

        def sav(orders_):
            return sum(E.saving(p, o.size) for o in orders_)

        def ded_cost(orders_):
            um_ = sum(UM[o.size] for o in orders_)
            return math.ceil(um_ / p.vehicle_um) * p.trip_cost if um_ else 0.0

        can_ded = zone == "GREEN" and dedicated_allowed
        ids = {o.id for o in along_set}
        rest = [o for o in grp if o.id not in ids]
        options = [(0.0, "NONE")]
        if along_set and sav(along_set) >= p.along_cost:
            options.append((sav(along_set) - p.along_cost, "ALONG"))
        if can_ded and sav(grp) >= ded_cost(grp):
            options.append((sav(grp) - ded_cost(grp), "DED_ALL"))
        if can_ded and along_set and rest and sav(along_set) >= p.along_cost \
                and sav(rest) >= ded_cost(rest):
            options.append((sav(along_set) - p.along_cost + sav(rest) - ded_cost(rest), "BOTH"))
        best = max(options, key=lambda x: x[0])[1]

        def add_trip(kind, orders_, cost, tag):
            trips.append({"kind": kind, "t": d, "n": len(orders_),
                          "um": sum(UM[o.size] for o in orders_),
                          "cost": cost, "saving": sav(orders_)})
            for o in orders_:
                mode[o.id] = tag

        if best == "ALONG":
            add_trip("ALONG", along_set, p.along_cost, "B_ALONG")
            served = ids
        elif best == "DED_ALL":
            add_trip("DEDICATED", grp, ded_cost(grp), "B_DED")
            served = {o.id for o in grp}
        elif best == "BOTH":
            add_trip("ALONG", along_set, p.along_cost, "B_ALONG")
            add_trip("DEDICATED", rest, ded_cost(rest), "B_DED")
            served = {o.id for o in grp}
        else:
            served = set()
        for o in grp:
            if o.id not in served:
                funnel["trip_cost"] += 1
                eta.pop(o.id, None)

    base_total = mesh_total = 0.0
    pvz_contrib = cap_gain = 0.0
    eta_base_sum = eta_mesh_sum = n_near = 0.0
    counts: Counter = Counter()
    for o in orders:
        b = E.baseline_cost(p, o.size, o.nearby)
        base_total += b
        m = mode.get(o.id, "HUB")
        counts[m] += 1
        if m == "HUB":
            mesh_total += b
        else:
            mesh_total += E.mesh_var(p, o.size)
            pvz_contrib += E.pvz_contribution(p, o.size)
            cap_gain += E.seller_capital_gain(p, eta[o.id])
        if o.nearby:
            n_near += 1
            eta_base_sum += p.eta_hub_h
            eta_mesh_sum += eta.get(o.id, p.eta_hub_h) if m != "HUB" else p.eta_hub_h
    mesh_total += sum(t["cost"] for t in trips)

    month = days_eff / 30
    saving_total = base_total - mesh_total
    mesh_orders = counts["A"] + counts["B_DED"] + counts["B_ALONG"]
    ded = [t for t in trips if t["kind"] == "DEDICATED"]
    alg = [t for t in trips if t["kind"] == "ALONG"]
    funnel_out = {"distance": funnel["distance"], "size": funnel["size"],
                  "zone": funnel["zone"], "capacity": funnel["capacity"],
                  "time": funnel["time"], "trip_cost": funnel["trip_cost"],
                  "unprofitable": funnel["unprofitable"],
                  "mode_A": counts["A"], "mode_B_dedicated": counts["B_DED"],
                  "mode_B_along": counts["B_ALONG"]}
    return {
        "orders": len(orders), "days": round(days_eff, 1), "zone": zone,
        "lambda_per_day": lam, "capacity_factor": cap_factor,
        "base_total": base_total, "mesh_total": mesh_total,
        "base_per_order": base_total / len(orders), "mesh_per_order": mesh_total / len(orders),
        "saving_month": saving_total / month,
        "saving_pct": 100 * saving_total / base_total if base_total else 0.0,
        "net_after_fixed_month": saving_total / month - p.fixed_cost_month,
        "mesh_orders": mesh_orders, "mesh_share_pct": 100 * mesh_orders / len(orders),
        "trips_dedicated": len(ded), "trips_along": len(alg),
        "avg_orders_per_dedicated": sum(t["n"] for t in ded) / len(ded) if ded else 0.0,
        "avg_orders_per_along": sum(t["n"] for t in alg) / len(alg) if alg else 0.0,
        "trip_cost_total_month": sum(t["cost"] for t in trips) / month,
        "pvz_total_month": pvz_contrib / month,
        "pvz_per_pvz_month": pvz_contrib / month / p.pvz_count,
        "eta_base_h": eta_base_sum / n_near if n_near else 0.0,
        "eta_mesh_h": eta_mesh_sum / n_near if n_near else 0.0,
        "seller_capital_gain_month": cap_gain / month,
        "funnel": funnel_out,
    }
