"""Сравнение схем, сценарии, чувствительность и карта взаимной выгоды."""
from dataclasses import replace
from statistics import mean

from .parameters import Params
from .simulation import simulate

SEEDS = (1, 2, 3, 4, 5)

NUMERIC = ("saving_month", "saving_pct", "net_after_fixed_month", "mesh_share_pct",
           "pvz_per_pvz_month", "pvz_total_month", "eta_base_h", "eta_mesh_h",
           "base_per_order", "mesh_per_order", "trips_dedicated", "trips_along",
           "avg_orders_per_dedicated", "avg_orders_per_along", "trip_cost_total_month",
           "seller_capital_gain_month", "lambda_per_day", "orders")


def run_avg(p: Params, seeds=SEEDS, dedicated_allowed: bool = True) -> dict:
    """Среднее по нескольким seed, чтобы убрать шум одного случайного прогона."""
    runs = [simulate(p, s, dedicated_allowed) for s in seeds]
    out = {k: mean(r[k] for r in runs) for k in NUMERIC}
    out["zone"] = max(set(r["zone"] for r in runs), key=[r["zone"] for r in runs].count)
    out["funnel"] = {k: mean(r["funnel"][k] for r in runs) for k in runs[0]["funnel"]}
    return out


def mutate(p: Params, name: str, factor: float) -> Params:
    if name == "share_S":
        s = min(0.87, p.share_S * factor)
        return replace(p, share_S=s, share_M=1 - s - p.share_L - p.share_KGT)
    if name == "nearby_share":
        return replace(p, nearby_share=min(1.0, p.nearby_share * factor))
    return replace(p, **{name: getattr(p, name) * factor})


TORNADO_PARAMS = [
    ("orders_per_day", "Число заказов в день (плотность)"),
    ("trip_cost_scale", "Стоимость рейса"),
    ("hub_scale", "Затраты пути через хаб"),
    ("pvz_fee_scale", "Ставки ПВЗ"),
    ("nearby_share", "Доля ближних заказов"),
    ("share_S", "Доля класса S"),
    ("shelf_hit_rate", "Доля выдач с полки (режим A)"),
    ("eta_hub_h", "Срок через хаб"),
    ("storage_days", "Срок хранения"),
]


def tornado(p: Params, metric: str, delta: float = 0.25) -> dict:
    base = run_avg(p)[metric]
    rows = []
    for name, label in TORNADO_PARAMS:
        lo = run_avg(mutate(p, name, 1 - delta))[metric]
        hi = run_avg(mutate(p, name, 1 + delta))[metric]
        rows.append({"param": name, "label": label, "low": lo, "high": hi,
                     "swing": abs(hi - lo)})
    rows.sort(key=lambda r: -r["swing"])
    return {"metric": metric, "base": base, "delta": delta, "rows": rows}


SCENARIOS = {
    "Пессимистичный": {"trip_cost_scale": 1.25, "hub_scale": 0.85, "orders_per_day": 0.75,
                       "nearby_share": 0.90, "pvz_fee_scale": 1.15, "shelf_hit_rate": 0.5},
    "Базовый": {},
    "Оптимистичный": {"trip_cost_scale": 0.85, "hub_scale": 1.15, "orders_per_day": 1.25,
                      "nearby_share": 1.08, "pvz_fee_scale": 0.90, "shelf_hit_rate": 1.5},
}


def scenarios(p: Params) -> dict:
    out = {}
    for label, mult in SCENARIOS.items():
        q = p
        for name, f in mult.items():
            q = mutate(q, name, f)
        out[label] = run_avg(q)
    return out


def compare_schemes(p: Params) -> dict:
    """Базовая схема против двух вариантов mesh на одних и тех же заказах."""
    return {
        "mesh_dedicated_only": run_avg(replace(p, along_available=False)),
        "mesh_with_along": run_avg(p),
    }


def mutual_map(p: Params, orders_grid, fee_grid, seeds=(1, 2, 3)):
    """Карта взаимной выгоды: плотность × ставка ПВЗ.

    0 — mesh не включается; 1 — ПВЗ ниже минимума; 2 — выигрывают все стороны;
    3 — выигрывают все и пилот покрывает постоянные расходы.
    """
    grid = []
    for opd in orders_grid:
        row = []
        for fee in fee_grid:
            r = run_avg(replace(p, orders_per_day=opd, pvz_fee_scale=fee), seeds)
            if r["mesh_share_pct"] < 0.5 or r["saving_month"] <= 0:
                cell = 0
            elif r["pvz_per_pvz_month"] < p.pvz_min_month:
                cell = 1
            elif r["net_after_fixed_month"] >= 0:
                cell = 3
            else:
                cell = 2
            row.append(cell)
        grid.append(row)
    return grid
