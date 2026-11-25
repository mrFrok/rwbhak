"""Формулы юнит-экономики. Один расчёт — один код: им пользуются API, симулятор и тесты."""

from __future__ import annotations

from decimal import Decimal

from . import parameters as P
from .parameters import q


def hub_cost(size_code: str, storage_days: int = P.HUB_STORAGE_DAYS) -> Decimal:
    """Устранимые затраты базовой схемы: обработка, хранение, два плеча."""
    size = P.get_size(size_code)
    return q(
        P.HUB_PROCESSING * size.k_op
        + P.HUB_STORAGE_PER_UM_DAY * size.um * storage_days
        + P.HUB_LINEHAUL * size.k_tr
        + P.HUB_LAST_MILE * size.k_tr
    )


def pvz_operations_cost(size_code: str, storage_days: int = P.MESH_STORAGE_DAYS) -> Decimal:
    """Выплаты ПВЗ за операции: приёмка + хранение + сборка."""
    size = P.get_size(size_code)
    return q(
        P.MESH_ACCEPTANCE * size.k_op
        + P.MESH_STORAGE_PER_UM_DAY * size.um * storage_days
        + P.MESH_PICKING * size.k_op
    )


def mesh_variable_cost(
    size_code: str,
    storage_days: int = P.MESH_STORAGE_DAYS,
    on_time: bool = True,
    shelf_sale: bool = False,
) -> Decimal:
    """Себестоимость mesh без стоимости рейса.

    Включает выплаты ПВЗ, бонус за выдачу в срок и резерв на возвраты.
    Режим A (shelf_sale=True) дополнительно платит бонус «со своей полки» —
    оба бонуса суммируются (бизнес-модель v0.3, раздел 9.1): 52,00 ₽ для S.
    """
    size = P.get_size(size_code)
    operations = pvz_operations_cost(size_code, storage_days)
    bonus = q(operations * P.ON_TIME_BONUS_PCT) if on_time else Decimal("0")
    if shelf_sale:
        bonus += q(operations * P.SHELF_SALE_BONUS_PCT)
    return q(operations + bonus + size.returns_reserve)


def mesh_saving(size_code: str, storage_days: int = P.MESH_STORAGE_DAYS, shelf_sale: bool = False) -> Decimal:
    """Экономия mesh против хаба на одном заказе, до стоимости рейса."""
    return q(
        hub_cost(size_code, storage_days)
        - mesh_variable_cost(size_code, storage_days, shelf_sale=shelf_sale)
    )


def saving_per_um(size_code: str) -> Decimal:
    size = P.get_size(size_code)
    return q(mesh_saving(size_code) / size.um)


def trip_cost(kind: str) -> Decimal:
    try:
        return P.TRIP_KIND_COST[kind]
    except KeyError as exc:
        raise ValueError(f"unknown trip kind: {kind}") from exc


def trip_cost_per_order(kind: str, orders: int) -> Decimal:
    if orders <= 0:
        raise ValueError("trip must contain at least one order")
    return q(trip_cost(kind) / orders)


def order_cost_mesh(size_code: str, kind: str, orders_in_trip: int) -> Decimal:
    """Полная себестоимость mesh-заказа: переменные затраты + доля рейса."""
    return q(mesh_variable_cost(size_code) + trip_cost_per_order(kind, orders_in_trip))


def breakeven_orders(size_codes: list[str], kind: str) -> int:
    """Минимальное число заказов, при котором сумма экономии покрывает рейс."""
    if not size_codes:
        raise ValueError("empty flow")
    avg_saving = sum(mesh_saving(code) for code in size_codes) / len(size_codes)
    if avg_saving <= 0:
        raise ValueError("mesh is not cheaper than hub for this flow")
    cost = trip_cost(kind)
    count = int((cost / avg_saving).to_integral_value(rounding="ROUND_CEILING"))
    # проверяем точным перебором с учётом округления денег
    while count > 1 and avg_saving * (count - 1) >= cost:
        count -= 1
    while avg_saving * count < cost:
        count += 1
    return count


def trip_result(size_codes: list[str], kind: str) -> dict[str, object]:
    """Себестоимость заказа и эффект рейса для конкретного состава."""
    if not size_codes:
        raise ValueError("empty trip")
    count = len(size_codes)
    mesh_costs = [mesh_variable_cost(code) for code in size_codes]
    hub_costs = [hub_cost(code) for code in size_codes]
    total_mesh = sum(mesh_costs, Decimal("0")) + trip_cost(kind)
    total_hub = sum(hub_costs, Decimal("0"))
    capacity = sum(P.get_size(code).um for code in size_codes)
    return {
        "orders": count,
        "capacity_um": capacity,
        "cost_mesh_per_order": q(total_mesh / count),
        "cost_hub_per_order": q(total_hub / count),
        "effect_per_trip": q(total_hub - total_mesh),
        "mesh_cheaper": total_mesh < total_hub,
    }


def pvz_revenue(size_code: str, storage_days: int = P.MESH_STORAGE_DAYS) -> Decimal:
    return pvz_operations_cost(size_code, storage_days)


def pvz_contribution(size_code: str, storage_days: int = P.MESH_STORAGE_DAYS) -> Decimal:
    """Вклад ПВЗ: выручка за операции минус труд и расходники.

    Бонусы за срок и продажу со своей полки сюда не входят: их считаем отдельно
    по фактическим событиям, чтобы не удваивать при расчёте режима B.
    """
    size = P.get_size(size_code)
    labor = q(P.PVZ_LABOR_COST_HOUR * Decimal(size.labor_minutes) / Decimal(60))
    return q(pvz_revenue(size_code, storage_days) - labor - size.overhead)


def contribution_per_um_day(size_code: str, storage_days: int = P.MESH_STORAGE_DAYS) -> Decimal:
    size = P.get_size(size_code)
    return q(pvz_contribution(size_code, storage_days) / (size.um * storage_days))


def seller_storage_fee(size_code: str, days: int) -> Decimal:
    """Прогрессивный тариф хранения для продавца: первые 3 дня бесплатно."""
    size = P.get_size(size_code)
    total = Decimal("0")
    start = P.SELLER_FREE_DAYS + 1
    for day in range(start, days + 1):
        rate = next(rate for end_day, rate in P.STORAGE_TIERS if end_day is None or day <= end_day)
        total += rate * size.um
    return q(total)


def pvz_storage_payout(size_code: str, days: int) -> Decimal:
    """ПВЗ получает за место с первого дня, даже пока продавец не платит."""
    size = P.get_size(size_code)
    return q(P.MESH_STORAGE_PER_UM_DAY * size.um * max(days, 0))


def on_time_bonus(size_code: str, storage_days: int = P.MESH_STORAGE_DAYS) -> Decimal:
    return q(pvz_operations_cost(size_code, storage_days) * P.ON_TIME_BONUS_PCT)


def shelf_sale_bonus(size_code: str, storage_days: int = P.MESH_STORAGE_DAYS) -> Decimal:
    return q(pvz_operations_cost(size_code, storage_days) * P.SHELF_SALE_BONUS_PCT)


def seller_logistics_fee(size_code: str) -> Decimal:
    """Логистика до покупателя: фиксированный тариф, не выше хабового."""
    return P.SELLER_LOGISTICS_FEE.get(size_code, Decimal("0"))


def seller_margin(
    size_code: str,
    price: Decimal,
    unit_cost: Decimal,
    days: int = P.MESH_STORAGE_DAYS,
) -> dict[str, Decimal]:
    """Полная юнит-экономика продавца (бизнес-модель v0.3, раздел 9.2).

    Включает комиссию маркетплейса 15%, эквайринг 1,5%, логистику до покупателя,
    платное хранение с 4-го дня, удельный расход на возвраты и налог УСН 6%.
    """
    commission = q(price * P.MP_COMMISSION_PCT)
    acquiring = q(price * P.ACQUIRING_PCT)
    logistics = seller_logistics_fee(size_code)
    storage = seller_storage_fee(size_code, days)
    returns_cost = q((logistics + P.RETURN_LOGISTICS_FEE) * P.RETURN_RATE)
    tax = q(price * P.SELLER_TAX_PCT)
    margin = q(price - unit_cost - commission - acquiring - logistics - storage - returns_cost - tax)
    return {
        "price": q(price),
        "unit_cost": q(unit_cost),
        "commission": commission,
        "acquiring": acquiring,
        "logistics": logistics,
        "storage": storage,
        "returns": returns_cost,
        "tax": tax,
        "margin": margin,
    }


def mix_avg_saving() -> Decimal:
    """Средняя экономия до рейса для потока пилота (70% S + 30% M): 68,81 ₽."""
    weighted = sum(
        (weight * mesh_saving(code) for code, weight in P.DEMO_MIX.items()),
        Decimal("0"),
    )
    return q(weighted)


def pilot_month_effect(orders_per_trip: int, kind: str) -> Decimal:
    """Валовой месячный эффект пилота до постоянных расходов (раздел 11)."""
    if orders_per_trip <= 0:
        raise ValueError("orders_per_trip must be positive")
    return q(P.TRIPS_PER_MONTH * (Decimal(orders_per_trip) * mix_avg_saving() - trip_cost(kind)))


def pilot_breakeven_orders(kind: str) -> int:
    """Заказов в рейсе, при которых пилот окупает постоянные расходы."""
    need = q(P.PILOT_FIXED_COST_MONTH / P.TRIPS_PER_MONTH + trip_cost(kind))
    avg = mix_avg_saving()
    count = int((need / avg).to_integral_value(rounding="ROUND_CEILING"))
    while count > 1 and pilot_month_effect(count - 1, kind) >= P.PILOT_FIXED_COST_MONTH:
        count -= 1
    while pilot_month_effect(count, kind) < P.PILOT_FIXED_COST_MONTH:
        count += 1
    return count


def pilot_summary(rows: tuple[int, ...] = (40, 62, 66, 100, 116, 150)) -> dict[str, object]:
    """Экономика пилота: пороги и месячный эффект после постоянных расходов."""
    return {
        "fixed_cost_month": P.PILOT_FIXED_COST_MONTH,
        "trips_per_month": P.TRIPS_PER_MONTH,
        "avg_saving": mix_avg_saving(),
        "breakeven_dedicated": pilot_breakeven_orders(P.TRIP_KIND_DEDICATED),
        "breakeven_along": pilot_breakeven_orders(P.TRIP_KIND_ALONG),
        "rows": [
            {
                "orders": orders,
                "effect_dedicated": q(pilot_month_effect(orders, P.TRIP_KIND_DEDICATED) - P.PILOT_FIXED_COST_MONTH),
                "effect_along": q(pilot_month_effect(orders, P.TRIP_KIND_ALONG) - P.PILOT_FIXED_COST_MONTH),
            }
            for orders in rows
        ],
    }

