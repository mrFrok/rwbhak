"""Реестр допущений и тарифов.

Все числа модели собраны здесь. Логика (`economics`, `solver`, `ledger`) читает только
этот модуль, поэтому замена допущений на реальные данные не требует правки расчётов.
Значения — допущения команды, а не тарифы RWB.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

MONEY = Decimal("0.01")


def q(value: object) -> Decimal:
    """Округлить деньги до копеек (half-up)."""
    return Decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class SizeClass:
    code: str
    title: str
    um: int
    ops_factor: Decimal
    freight_factor: Decimal
    labor_minutes: int
    overhead: Decimal
    returns_reserve: Decimal

    @property
    def mesh_allowed(self) -> bool:
        return self.code in MESH_SIZE_CODES


SIZE_CLASSES: dict[str, SizeClass] = {
    "S": SizeClass("S", "Пакет, аксессуар", 1, Decimal("1.0"), Decimal("1.0"), 3, Decimal("5"), Decimal("6")),
    "M": SizeClass("M", "Обувная коробка", 3, Decimal("1.3"), Decimal("1.5"), 4, Decimal("15"), Decimal("6.27")),
    "L": SizeClass("L", "Крупная коробка", 8, Decimal("1.8"), Decimal("2.5"), 6, Decimal("40"), Decimal("5.22")),
}
MESH_SIZE_CODES = ("S", "M")
SPECIAL_SIZE = "KGT"

# --- Базовая схема через хаб, ₽ на заказ -------------------------------------
HUB_PROCESSING = Decimal("25")          # × ops_factor
HUB_STORAGE_PER_UM_DAY = Decimal("3")
HUB_STORAGE_DAYS = 3
HUB_LINEHAUL = Decimal("40")            # × freight_factor, продавец → хаб
HUB_LAST_MILE = Decimal("35")           # × freight_factor, хаб → ПВЗ

# --- Mesh: операции в ПВЗ, ₽ на заказ ---------------------------------------
MESH_ACCEPTANCE = Decimal("10")         # × ops_factor
MESH_STORAGE_PER_UM_DAY = Decimal("3")  # ПВЗ получает с 1-го дня
MESH_STORAGE_DAYS = 3
MESH_PICKING = Decimal("21")            # × ops_factor
ON_TIME_BONUS_PCT = Decimal("0.10")     # +10% к выплатам ПВЗ за заказ
SHELF_SALE_BONUS_PCT = Decimal("0.05")  # режим A, +5% к выплатам за операции

# --- Рейс -------------------------------------------------------------------
TRIP_COST_DEDICATED = Decimal("4500")   # 240 км × 12 ₽ + 6 ч × 270 ₽
TRIP_COST_ALONG = Decimal("750")        # крюк 40 км + остановка
TRIP_CAPACITY_UM = 300
TRIP_ALONG_CAPACITY_UM = 60             # свободное место на уже идущем рейсе
TRIP_DISTANCE_KM = 120
TRIP_KIND_DEDICATED = "DEDICATED"
TRIP_KIND_ALONG = "ALONG"
TRIP_KIND_COST = {
    TRIP_KIND_DEDICATED: TRIP_COST_DEDICATED,
    TRIP_KIND_ALONG: TRIP_COST_ALONG,
}

# --- ПВЗ --------------------------------------------------------------------
PVZ_CAPACITY_UM = 200
PVZ_RESERVE_PCT = Decimal("0.15")     # доступно ~170 УМ
PVZ_M_UM_SHARE_LIMIT = Decimal("0.5")  # доля M не больше 50% места
PVZ_LABOR_COST_HOUR = Decimal("400")

# --- Сроки, зоны, границы ---------------------------------------------------
HUB_ETA_H = 48
MESH_ETA_OVERHEAD_H = 5   # путь и выдача после рейса
MESH_ETA_SHELF_H = 4      # режим A
DELTA_T_H = 0             # mesh не должен быть медленнее хаба
MAX_MESH_DISTANCE_KM = 300
ZONE_GREEN = "GREEN"
ZONE_YELLOW = "YELLOW"
ZONE_RED = "RED"
ZONE_CLASSES = (ZONE_GREEN, ZONE_YELLOW, ZONE_RED)
MESH_ZONES = (ZONE_GREEN, ZONE_YELLOW)
ZONE_MIN_LAMBDA = {ZONE_GREEN: Decimal("38"), ZONE_YELLOW: Decimal("7")}
TRIP_INTERVAL_DAYS = Decimal("1.75")  # 4 рейса в неделю

# --- Хранение и неликвид ----------------------------------------------------
SELLER_FREE_DAYS = 3
STORAGE_TIERS: tuple[tuple[int | None, Decimal], ...] = (
    (7, Decimal("3")),    # дни 4-7, ₽ за УМ-день
    (14, Decimal("6")),   # дни 8-14
    (None, Decimal("10")),  # дни 15+
)
NO_SALES_ALERT_DAY = 7
REMOVAL_DAY = 15
REMOVAL_FEE = Decimal("35")          # вывоз единицы на хаб, дни 15+

# --- Продавец: комиссии, логистика (ANALYTICS.md A46–A48, контракт API) -------
MP_COMMISSION_PCT = Decimal("0.15")  # комиссия маркетплейса
ACQUIRING_PCT = Decimal("0.015")    # расширенный расчёт v0.3
SELLER_LOGISTICS_FEE = Decimal("60")  # тариф логистики продавцу × freight_factor
RETURN_LOGISTICS_FEE = Decimal("50")  # обратная логистика при отказе
RETURN_RATE = Decimal("0.05")         # доля возвратов
SELLER_TAX_PCT = Decimal("0.06")    # расширенный расчёт v0.3
TRUNK_STUB_COST = Decimal("120")    # дальний заказ через хаб

# --- Пилот (бизнес-модель v0.3, раздел 11) -----------------------------------
PILOT_FIXED_COST_MONTH = Decimal("60000")
TRIPS_PER_MONTH = Decimal("17.32")   # 4 рейса/нед × 4,33 нед

# --- Демо и симулятор -------------------------------------------------------
SEED = 42
DEMO_MIX = {"S": Decimal("0.7"), "M": Decimal("0.3")}
DEMO_ORDERS = 3000
DEMO_DAYS = 30
DEMO_FAR_SHARE = Decimal("0.15")
DEMO_RETURN_SHARE = Decimal("0.05")
# Распределение дальних заказов: другой регион → всегда режим C.

# --- Реестр допущений для GET /params ---------------------------------------
ASSUMPTIONS: list[dict[str, object]] = [
    {"code": "hub.s", "name": "Устранимые затраты хаба, класс S", "value": 109, "unit": "₽/заказ"},
    {"code": "hub.m", "name": "Устранимые затраты хаба, класс M", "value": 172, "unit": "₽/заказ"},
    {"code": "hub.l", "name": "Устранимые затраты хаба, класс L", "value": 304.5, "unit": "₽/заказ"},
    {"code": "trip.dedicated", "name": "Выделенный рейс 120 км, туда-обратно", "value": 4500, "unit": "₽/рейс"},
    {"code": "trip.along", "name": "Приращение при попутной загрузке", "value": 750, "unit": "₽/рейс"},
    {"code": "pvz.acceptance", "name": "Приёмка единицы", "value": 10, "unit": "₽ × k_оп"},
    {"code": "pvz.storage", "name": "Хранение в ПВЗ", "value": 3, "unit": "₽/УМ-день"},
    {"code": "pvz.picking", "name": "Сборка заказа", "value": 21, "unit": "₽ × k_оп"},
    {"code": "size.s", "name": "Габарит S", "value": 1, "unit": "УМ"},
    {"code": "size.m", "name": "Габарит M", "value": 3, "unit": "УМ"},
    {"code": "size.l", "name": "Габарит L", "value": 8, "unit": "УМ"},
    {"code": "trip.capacity", "name": "Вместимость рейса", "value": 300, "unit": "УМ"},
    {"code": "pvz.capacity", "name": "Ёмкость подсобки", "value": 200, "unit": "УМ"},
    {"code": "pvz.reserve", "name": "Резерв места", "value": 15, "unit": "%"},
    {"code": "storage.avg_days", "name": "Средний срок хранения", "value": 3, "unit": "дн"},
    {"code": "returns.share", "name": "Доля возвратов", "value": 5, "unit": "%"},
    {"code": "labor.rate", "name": "Труд сотрудника ПВЗ", "value": 400, "unit": "₽/ч"},
    {"code": "eta.hub", "name": "Срок через хаб", "value": 48, "unit": "ч"},
    {"code": "eta.mesh_overhead", "name": "Путь и выдача после рейса", "value": 5, "unit": "ч"},
    {"code": "flow.mix", "name": "Состав потока пилота", "value": "70% S + 30% M", "unit": ""},
    {"code": "zone.green", "name": "Порог зоны GREEN", "value": 38, "unit": "заказов/день"},
    {"code": "zone.yellow", "name": "Порог зоны YELLOW", "value": 7, "unit": "заказов/день"},
    {"code": "seller.commission", "name": "Комиссия маркетплейса", "value": 15, "unit": "%"},
    {"code": "seller.acquiring", "name": "Эквайринг", "value": 1.5, "unit": "%"},
    {"code": "seller.logistics", "name": "Базовый тариф логистики продавцу × коэффициент перевозки", "value": float(SELLER_LOGISTICS_FEE), "unit": "₽/заказ"},
    {"code": "seller.return_logistics", "name": "Обратная логистика при отказе", "value": 50, "unit": "₽/ед."},
    {"code": "seller.tax", "name": "Налог продавца (УСН с выручки)", "value": 6, "unit": "%"},
    {"code": "storage.removal_fee", "name": "Вывоз неликвида на хаб, 15+ дни", "value": 35, "unit": "₽/ед."},
    {"code": "pilot.fixed_cost", "name": "Постоянные расходы пилота", "value": 60000, "unit": "₽/мес"},
    {"code": "pilot.trips_per_month", "name": "Рейсов в месяц (4 в неделю)", "value": 17.32, "unit": "рейс/мес"},
]


def get_size(code: str) -> SizeClass:
    try:
        return SIZE_CLASSES[code]
    except KeyError as exc:
        raise ValueError(f"unknown size class: {code}") from exc


def registry() -> list[dict[str, object]]:
    """Реестр допущений с пометкой источника."""
    return [
        {**item, "source": "допущение команды, не тариф RWB"}
        for item in ASSUMPTIONS
    ]
