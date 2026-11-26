"""Анализ модели: сравнение схем, сценарии, чувствительность, карта выгоды."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from .model import ModelParams, metrics, run_avg, scenario_params, simulate

D = Decimal


def _flat(metrics_row: dict[str, object]) -> dict[str, object]:
    return {
        "cost_per_order": metrics_row["cost_per_order_mesh"],
        "saving_month": metrics_row["saving_month"],
        "saving_pct": metrics_row["saving_pct"],
        "after_fixed_month": metrics_row["after_fixed_month"],
        "mesh_share": metrics_row["mesh_share"],
        "near_eta_h": metrics_row["near_eta_h"],
        "pvz_contribution_month": metrics_row["pvz_contribution_month"],
        "capital_effect_month": metrics_row["capital_effect_month"],
        "trips_along": metrics_row["trips_along"],
        "trips_dedicated": metrics_row["trips_dedicated"],
    }


def compare_schemes(params: ModelParams, seeds: tuple[int, ...] = (1, 2, 3, 4, 5)) -> dict[str, object]:
    """Три схемы на одном потоке: хаб, только выделенные, с попутными."""
    base = run_avg(params, seeds)
    hub = {
        "cost_per_order": base["cost_per_order_hub"],
        "saving_month": D("0"),
        "saving_pct": D("0"),
        "after_fixed_month": -params.fixed_cost_month,
        "mesh_share": D("0"),
        "near_eta_h": params.eta_hub_h,
        "pvz_contribution_month": D("0"),
        "capital_effect_month": D("0"),
        "trips_along": 0,
        "trips_dedicated": 0,
    }
    dedicated = _flat(run_avg(replace(params, along_available=False), seeds))
    along = _flat(base)
    rows = [
        {
            "metric": "cost_per_order",
            "hub": hub["cost_per_order"],
            "dedicated": dedicated["cost_per_order"],
            "along": along["cost_per_order"],
        },
        {
            "metric": "saving_month",
            "hub": hub["saving_month"],
            "dedicated": dedicated["saving_month"],
            "along": along["saving_month"],
        },
        {
            "metric": "saving_pct",
            "hub": hub["saving_pct"],
            "dedicated": dedicated["saving_pct"],
            "along": along["saving_pct"],
        },
        {
            "metric": "after_fixed_month",
            "hub": hub["after_fixed_month"],
            "dedicated": dedicated["after_fixed_month"],
            "along": along["after_fixed_month"],
        },
        {
            "metric": "mesh_share",
            "hub": hub["mesh_share"],
            "dedicated": dedicated["mesh_share"],
            "along": along["mesh_share"],
        },
        {
            "metric": "near_eta_h",
            "hub": hub["near_eta_h"],
            "dedicated": dedicated["near_eta_h"],
            "along": along["near_eta_h"],
        },
        {
            "metric": "pvz_contribution_month",
            "hub": hub["pvz_contribution_month"],
            "dedicated": dedicated["pvz_contribution_month"],
            "along": along["pvz_contribution_month"],
        },
        {
            "metric": "capital_effect_month",
            "hub": hub["capital_effect_month"],
            "dedicated": dedicated["capital_effect_month"],
            "along": along["capital_effect_month"],
        },
        {
            "metric": "trips_along",
            "hub": 0,
            "dedicated": dedicated["trips_along"],
            "along": along["trips_along"],
        },
        {
            "metric": "trips_dedicated",
            "hub": 0,
            "dedicated": dedicated["trips_dedicated"],
            "along": along["trips_dedicated"],
        },
    ]
    return {
        "params": {
            "orders_per_day": params.orders_per_day,
            "nearby_share": params.nearby_share,
            "days": params.days,
            "seeds": list(seeds),
            "zone": "auto",
        },
        "hub": hub,
        "dedicated": dedicated,
        "along": along,
        "rows": rows,
    }


def scenarios(params: ModelParams, seeds: tuple[int, ...] = (1, 2, 3, 4, 5)) -> list[dict[str, object]]:
    result = []
    for kind, title in (("pessimistic", "Пессимистичный"), ("base", "Базовый"), ("optimistic", "Оптимистичный")):
        params_kind = scenario_params(params, kind)
        row = run_avg(params_kind, seeds)
        result.append(
            {
                "name": kind,
                "title": title,
                "zone": __import__("core.model", fromlist=["classify_zone"]).classify_zone(params_kind.zone_lambda()),
                "saving_month": row["saving_month"],
                "saving_pct": row["saving_pct"],
                "after_fixed_month": row["after_fixed_month"],
                "pvz_contribution_month": row["pvz_contribution_month"],
                "near_eta_h": row["near_eta_h"],
                "mesh_share": row["mesh_share"],
            }
        )
    return result


def _scale_share(params: ModelParams, factor: float) -> ModelParams:
    share_s = min(0.95, max(0.05, params.share_S * factor))
    delta = share_s - params.share_S
    share_m = min(0.95, max(0.0, params.share_M - delta))
    return replace(params, share_S=share_s, share_M=share_m)


TORNADO_PARAMS = (
    ("Затраты пути через хаб", lambda p, f: replace(p, hub_scale=p.hub_scale * D(str(f)))),
    ("Число заказов в день (плотность)", lambda p, f: replace(p, orders_per_day=p.orders_per_day * f)),
    ("Ставки ПВЗ", lambda p, f: replace(p, pvz_fee_scale=p.pvz_fee_scale * D(str(f)))),
    ("Доля ближних заказов", lambda p, f: replace(p, nearby_share=min(1.0, max(0.0, p.nearby_share * f))) ),
    ("Срок через хаб", lambda p, f: replace(p, eta_hub_h=p.eta_hub_h * D(str(f)))),
    ("Стоимость рейса", lambda p, f: replace(p, trip_cost_scale=p.trip_cost_scale * D(str(f)))),
    ("Доля класса S", lambda p, f: _scale_share(p, f)),
    ("Доля выдач с полки (режим A)", lambda p, f: replace(p, shelf_hit_rate=min(1.0, p.shelf_hit_rate * f))),
    ("Срок хранения", lambda p, f: replace(p, storage_days=max(1, round(p.storage_days * f)))),
)


def tornado(
    params: ModelParams, factor: float = 0.25, seeds: tuple[int, ...] = (1, 2, 3, 4, 5)
) -> dict[str, object]:
    base = run_avg(params, seeds)
    base_saving = base["saving_month"]
    rows = []
    for title, mutate in TORNADO_PARAMS:
        low = run_avg(mutate(params, 1 - factor), seeds)["saving_month"]
        high = run_avg(mutate(params, 1 + factor), seeds)["saving_month"]
        rows.append(
            {
                "parameter": title,
                "minus": low,
                "plus": high,
                "range": abs(high - low),
            }
        )
    rows.sort(key=lambda row: row["range"], reverse=True)
    return {"base_saving_month": base_saving, "factor_pct": factor * 100, "rows": rows}


def mutual_map(
    params: ModelParams,
    orders_grid: tuple[float, ...] = (20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160),
    fee_grid: tuple[float, ...] = (0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7),
    seed: int = 1,
) -> dict[str, object]:
    rows = []
    green_cells = 0
    covered_cells = 0
    for orders in orders_grid:
        cells = []
        for fee in fee_grid:
            variant = replace(params, orders_per_day=orders, pvz_fee_scale=D(str(fee)))
            result = metrics(variant, simulate(variant, seed))
            saving = result["saving_month"]
            pvz = result["pvz_contribution_month"]
            if saving > 0 and pvz >= params.pvz_min_month:
                status = "COVERED" if result["after_fixed_month"] >= 0 else "MUTUAL"
            elif saving > 0:
                status = "PVZ_LOW"
            else:
                status = "OFF"
            if status in ("MUTUAL", "COVERED"):
                green_cells += 1
            if status == "COVERED":
                covered_cells += 1
            cells.append({"fee_scale": fee, "status": status})
        rows.append({"orders_per_day": orders, "cells": cells})
    return {
        "orders_grid": list(orders_grid),
        "fee_grid": list(fee_grid),
        "rows": rows,
        "mutual_cells": green_cells,
        "covered_cells": covered_cells,
        "total_cells": len(orders_grid) * len(fee_grid),
    }
