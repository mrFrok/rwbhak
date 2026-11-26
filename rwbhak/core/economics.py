"""Формулы затрат: хаб, mesh, вклад ПВЗ. Источник правды для всех цифр проекта."""
import math
from .parameters import Params, UM, K_OP, K_TR, LABOR_MIN


def hub_cost(p: Params, cls: str) -> float:
    """Устранимые затраты базовой схемы (через хаб) на один заказ."""
    ops = p.hub_proc * K_OP[cls]
    legs = (p.hub_leg_seller + p.hub_last_mile) * K_TR[cls]
    storage = p.hub_storage_rate * UM[cls] * p.storage_days
    return p.hub_scale * (ops + legs) + storage


def pvz_revenue(p: Params, cls: str) -> float:
    k = K_OP[cls]
    return p.pvz_fee_scale * (p.pvz_receive * k
                              + p.pvz_storage_rate * UM[cls] * p.storage_days
                              + p.pvz_assemble * k)


def mesh_var(p: Params, cls: str) -> float:
    """Затраты mesh на заказ без стоимости рейса."""
    return pvz_revenue(p, cls) + p.mesh_other * K_OP[cls]


def saving(p: Params, cls: str) -> float:
    """Экономия до рейса: хаб − mesh."""
    return hub_cost(p, cls) - mesh_var(p, cls)


def pvz_contribution(p: Params, cls: str) -> float:
    labor = p.labor_rate_hour / 60 * LABOR_MIN[cls]
    space = p.pvz_space_per_um_day * UM[cls] * p.storage_days
    return pvz_revenue(p, cls) - labor - space


def baseline_cost(p: Params, cls: str, nearby: bool) -> float:
    """Базовая схема: ближний заказ идёт через хаб, дальний ещё и по магистрали."""
    return hub_cost(p, cls) + (0.0 if nearby else p.trunk_stub)


def breakeven_orders(p: Params, avg_saving: float, along: bool = False) -> int:
    """Минимум заказов в рейсе, при котором рейс окупается."""
    cost = p.along_cost if along else p.trip_cost
    return math.ceil(cost / avg_saving) if avg_saving > 0 else 10**9


def mixed_saving(p: Params, share_s: float = 0.7, share_m: float = 0.3) -> float:
    return share_s * saving(p, "S") + share_m * saving(p, "M")


def seller_capital_gain(p: Params, eta_mesh_h: float) -> float:
    """Выигрыш продавца в замороженном капитале за сэкономленное время, ₽ на заказ."""
    days = max(0.0, (p.eta_hub_h - eta_mesh_h) / 24)
    return p.seller_unit_cost * p.capital_rate_year / 365 * days
