"""Выбор варианта рейса: одна функция для API и симулятора (ТЗ backend, T7).

Перебираем, что выпускать по коридору: только попутную загрузку, только
выделенный рейс, оба или ничего. Критерий — чистая экономия против хаба.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from . import parameters as P
from .economics import mesh_saving, trip_cost


@dataclass(frozen=True)
class TripVariant:
    kind: str                 # DEDICATED / ALONG
    capacity_um: int
    cost: Decimal


VARIANTS = (
    TripVariant(P.TRIP_KIND_ALONG, P.TRIP_ALONG_CAPACITY_UM, P.TRIP_COST_ALONG),
    TripVariant(P.TRIP_KIND_DEDICATED, P.TRIP_CAPACITY_UM, P.TRIP_COST_DEDICATED),
)


def _fill(sizes: list[str], capacity_um: int) -> list[int]:
    """Индексы заказов, влезающих в машину по УМ, в порядке очереди."""
    chosen: list[int] = []
    used = 0
    for index, size in enumerate(sizes):
        um = P.get_size(size).um
        if used + um > capacity_um:
            continue
        chosen.append(index)
        used += um
    return chosen


def plan_trip(sizes: list[str], zone_class: str = P.ZONE_GREEN) -> dict[str, object]:
    """Выбрать состав отправления для очереди заказов режима B.

    Возвращает список рейсов (kind + индексы заказов + экономика) и индексы
    заказов, которые не поехали (не влезли или рейс не окупается).
    """
    if not sizes:
        return {"trips": [], "leftover": [], "saving_total": Decimal("0")}

    allowed = (
        (VARIANTS[0],) if zone_class == P.ZONE_YELLOW else VARIANTS
        if zone_class in P.MESH_ZONES else ()
    )
    best: dict[str, object] | None = None
    for variant in allowed:
        assigned = _fill(sizes, variant.capacity_um)
        saving = sum((mesh_saving(sizes[i]) for i in assigned), Decimal("0"))
        if saving < variant.cost:
            continue
        candidate = {
            "trips": [{"kind": variant.kind, "order_idx": assigned, "saving": saving}],
            "leftover": [i for i in range(len(sizes)) if i not in set(assigned)],
            "saving_total": saving - variant.cost,
        }
        if best is None or candidate["saving_total"] > best["saving_total"]:  # type: ignore[operator]
            best = candidate

    if best is not None:
        return best

    # Ни один вариант не окупается: пробуем «оба» — попутная загрузка плюс
    # выделенный рейс на остаток очереди.
    if zone_class in P.MESH_ZONES:
        along, dedicated = VARIANTS
        first = _fill(sizes, along.capacity_um)
        rest = [i for i in range(len(sizes)) if i not in set(first)]
        second = _fill(rest, dedicated.capacity_um)
        saving = sum((mesh_saving(sizes[i]) for i in first + second), Decimal("0"))
        if saving >= along.cost + dedicated.cost and second:
            return {
                "trips": [
                    {"kind": along.kind, "order_idx": first, "saving": sum((mesh_saving(sizes[i]) for i in first), Decimal("0"))},
                    {"kind": dedicated.kind, "order_idx": second, "saving": sum((mesh_saving(sizes[i]) for i in second), Decimal("0"))},
                ],
                "leftover": [i for i in rest if i not in set(second)],
                "saving_total": saving - along.cost - dedicated.cost,
            }

    return {"trips": [], "leftover": list(range(len(sizes))), "saving_total": Decimal("0")}
