"""Печать порогов окупаемости: python -m core.breakeven"""
from .parameters import Params
from . import economics as E


def table(p: Params | None = None) -> str:
    p = p or Params()
    rows = ["Класс | хаб | mesh без рейса | экономия | вклад ПВЗ",
            "-----|-----|----------------|----------|----------"]
    for c in ("S", "M", "L"):
        rows.append(f"{c:4} | {E.hub_cost(p, c):6.1f} | {E.mesh_var(p, c):14.1f} | "
                    f"{E.saving(p, c):8.1f} | {E.pvz_contribution(p, c):8.1f}")
    s = E.saving(p, "S")
    ms = E.mixed_saving(p)
    rows += ["",
             f"Стоимость рейса: {p.trip_cost:.0f} ₽, попутная загрузка: {p.along_cost:.0f} ₽",
             f"Порог, только S:       выделенный {E.breakeven_orders(p, s)}, попутный {E.breakeven_orders(p, s, True)}",
             f"Порог, поток 70/30:    выделенный {E.breakeven_orders(p, ms)}, попутный {E.breakeven_orders(p, ms, True)}"]
    return "\n".join(rows)


if __name__ == "__main__":
    print(table())
