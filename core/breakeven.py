"""Порог окупаемости рейса и справочные таблицы.

Запуск: `python -m core.breakeven`
"""

from __future__ import annotations

from decimal import Decimal

from . import parameters as P
from .economics import breakeven_orders, hub_cost, mesh_saving, mesh_variable_cost, trip_result
from .parameters import q

S_ONLY = ["S"]
MIXED = ["S"] * 7 + ["M"] * 3


def summary() -> dict[str, object]:
    return {
        "hub": {code: hub_cost(code) for code in ("S", "M", "L")},
        "mesh_without_trip": {code: mesh_variable_cost(code) for code in ("S", "M", "L")},
        "saving": {code: mesh_saving(code) for code in ("S", "M", "L")},
        "thresholds": {
            "dedicated_s": breakeven_orders(S_ONLY, P.TRIP_KIND_DEDICATED),
            "along_s": breakeven_orders(S_ONLY, P.TRIP_KIND_ALONG),
            "dedicated_mixed": breakeven_orders(MIXED, P.TRIP_KIND_DEDICATED),
            "along_mixed": breakeven_orders(MIXED, P.TRIP_KIND_ALONG),
        },
    }


def trip_table(counts: tuple[int, ...] = (30, 60, 66, 77, 100, 150)) -> list[dict[str, object]]:
    rows = []
    for n in counts:
        sizes = ["S"] * n
        result = trip_result(sizes, P.TRIP_KIND_DEDICATED)
        rows.append(
            {
                "orders": n,
                "mesh_per_order": result["cost_mesh_per_order"],
                "hub_per_order": result["cost_hub_per_order"],
                "effect": result["effect_per_trip"],
                "decision": "mesh" if result["mesh_cheaper"] else "hub",
            }
        )
    return rows


def main() -> None:
    data = summary()
    print("Допущения: тарифы команды, не тарифы RWB\n")
    print("Себестоимость заказа через хаб, ₽:", ", ".join(f"{k} {v}" for k, v in data["hub"].items()))
    print("Mesh без рейса, ₽:", ", ".join(f"{k} {v}" for k, v in data["mesh_without_trip"].items()))
    print("Экономия до рейса, ₽:", ", ".join(f"{k} {v}" for k, v in data["saving"].items()))
    t = data["thresholds"]
    print(
        f"\nПорог рейса: только S — {t['dedicated_s']} выделенный / {t['along_s']} попутный; "
        f"поток 70% S + 30% M — {t['dedicated_mixed']} / {t['along_mixed']}"
    )
    print("\nВыделенный рейс, только S:")
    print(f"{'заказов':>8} {'mesh ₽':>8} {'хаб ₽':>8} {'эффект ₽':>10}  решение")
    for row in trip_table():
        print(
            f"{row['orders']:>8} {row['mesh_per_order']:>8} {row['hub_per_order']:>8} "
            f"{row['effect']:>10}  {row['decision']}"
        )


if __name__ == "__main__":
    main()
