"""Реестр допущений.

ВСЕ числа здесь — допущения команды, а не тарифы RWB. Каждое поле имеет единицу и
пояснение; `registry()` отдаёт их в API (`GET /params`) и на экран «Допущения».
Чтобы подставить реальные данные, меняется только этот файл.
"""
from dataclasses import dataclass, field, fields

CLASSES = ("S", "M", "L", "KGT")
MESH_ELIGIBLE = ("S", "M")           # классы, допущенные в mesh в пилоте
UM = {"S": 1, "M": 3, "L": 8, "KGT": 8}              # условные единицы места
K_OP = {"S": 1.0, "M": 1.3, "L": 1.8, "KGT": 1.8}    # коэффициент операций
K_TR = {"S": 1.0, "M": 1.5, "L": 2.5, "KGT": 2.5}    # коэффициент перевозки
LABOR_MIN = {"S": 3, "M": 4, "L": 6, "KGT": 6}       # минут труда на заказ в ПВЗ


def _f(value, unit="", note=""):
    return field(default=value, metadata={"unit": unit, "note": note})


@dataclass(frozen=True)
class Params:
    # --- затраты через хаб (на заказ класса S; остальные классы умножаются на k) ---
    hub_proc: float = _f(25.0, "₽", "Обработка на хабе × k_оп")
    hub_leg_seller: float = _f(40.0, "₽", "Плечо продавец → хаб × k_тр")
    hub_last_mile: float = _f(35.0, "₽", "Последняя миля хаб → ПВЗ × k_тр")
    hub_storage_rate: float = _f(3.0, "₽/УМ·день", "Хранение на хабе (принято равным ПВЗ)")
    hub_scale: float = _f(1.0, "×", "Множитель затрат хаба (для чувствительности)")
    # --- ставки и затраты ПВЗ ---
    pvz_receive: float = _f(10.0, "₽", "Приёмка × k_оп")
    pvz_storage_rate: float = _f(3.0, "₽/УМ·день", "Хранение в ПВЗ")
    pvz_assemble: float = _f(21.0, "₽", "Сборка × k_оп")
    mesh_other: float = _f(10.0, "₽", "Прочее: возвраты, вывоз, резерв × k_оп (затрата маркетплейса)")
    pvz_fee_scale: float = _f(1.0, "×", "Множитель ставок ПВЗ (приёмка, хранение, сборка)")
    labor_rate_hour: float = _f(400.0, "₽/час", "Труд сотрудника ПВЗ")
    pvz_space_per_um_day: float = _f(5 / 3, "₽/УМ·день", "Расходники и место")
    storage_days: float = _f(3.0, "дней", "Средний срок хранения")
    # --- рейсы ---
    trip_km: float = _f(240.0, "км", "Пробег рейса туда и обратно")
    cost_per_km: float = _f(12.0, "₽/км", "Стоимость км")
    trip_hours: float = _f(6.0, "ч", "Время водителя на рейс")
    driver_rate: float = _f(270.0, "₽/час", "Ставка водителя")
    along_km: float = _f(40.0, "км", "Крюк при попутной загрузке")
    along_hours: float = _f(1.0, "ч", "Остановка и погрузка при попутной загрузке")
    trip_cost_scale: float = _f(1.0, "×", "Множитель стоимости рейса (для чувствительности)")
    vehicle_um: float = _f(300.0, "УМ", "Вместимость выделенной машины")
    along_um: float = _f(60.0, "УМ", "Свободное место на уже идущем рейсе")
    along_available: bool = _f(True, "", "Есть ли попутные рейсы")
    # --- сроки ---
    eta_hub_h: float = _f(48.0, "ч", "Срок через хаб, ближний поток")
    eta_leg_h: float = _f(5.0, "ч", "Путь и выдача после отправки рейса")
    eta_shelf_h: float = _f(4.0, "ч", "Срок режима A (с полки)")
    delta_t_h: float = _f(0.0, "ч", "Допуск по сроку (0 = не хуже хаба)")
    trip_days: tuple = _f((0, 2, 4, 5), "", "Дни недели рейсов (0 = пн): 4 рейса в неделю")
    dep_hour: float = _f(8.0, "ч", "Час отправления рейса")
    # --- поток заказов ---
    days: int = _f(30, "дней", "Горизонт симуляции")
    orders_per_day: float = _f(100.0, "заказов/день", "Все заказы коридора")
    nearby_share: float = _f(0.85, "доля", "Доля ближних заказов (один коридор, до 300 км)")
    share_S: float = _f(0.60, "доля", "Доля класса S")
    share_M: float = _f(0.27, "доля", "Доля класса M")
    share_L: float = _f(0.08, "доля", "Доля класса L")
    share_KGT: float = _f(0.05, "доля", "Доля КГТ и особых товаров")
    shelf_hit_rate: float = _f(0.10, "доля", "Доля заказов, которые уже лежат в ПВЗ покупателя (режим A)")
    # --- сеть ---
    pvz_count: int = _f(4, "шт", "ПВЗ в пилоте")
    pvz_capacity_um: float = _f(200.0, "УМ", "Ёмкость подсобки")
    pvz_reserve: float = _f(0.15, "доля", "Резерв места под обычную выдачу")
    trunk_stub: float = _f(120.0, "₽", "Заглушка магистрали для дальних заказов (одинакова в обеих схемах)")
    # --- пилот ---
    fixed_cost_month: float = _f(60000.0, "₽/мес", "Постоянные расходы пилота")
    pvz_min_month: float = _f(5000.0, "₽/мес на ПВЗ", "Минимальный вклад, при котором ПВЗ согласен")
    # --- продавец ---
    seller_unit_cost: float = _f(600.0, "₽", "Средняя себестоимость единицы товара")
    capital_rate_year: float = _f(0.20, "доля/год", "Стоимость замороженного капитала продавца")
    seller_commission: float = _f(0.15, "доля от цены", "Комиссия маркетплейса (одинакова в обеих схемах)")
    seller_logistics_fee: float = _f(60.0, "₽", "Тариф логистики продавцу для класса S × k_тр (одинаков в обеих схемах)")
    return_rate: float = _f(0.05, "доля", "Доля возвратов")

    @property
    def trip_cost(self) -> float:
        return self.trip_cost_scale * (self.trip_km * self.cost_per_km + self.trip_hours * self.driver_rate)

    @property
    def along_cost(self) -> float:
        return self.trip_cost_scale * (self.along_km * self.cost_per_km + self.along_hours * self.driver_rate)

    @property
    def pvz_avail_um_total(self) -> float:
        return self.pvz_count * self.pvz_capacity_um * (1 - self.pvz_reserve)


def registry(p: Params | None = None) -> list[dict]:
    """Реестр допущений для API и экрана «Допущения»."""
    p = p or Params()
    return [
        {"id": f"A{i:02d}", "name": f.name, "value": getattr(p, f.name),
         "unit": f.metadata.get("unit", ""), "note": f.metadata.get("note", ""),
         "kind": "допущение команды"}
        for i, f in enumerate(fields(p), 1)
    ]
