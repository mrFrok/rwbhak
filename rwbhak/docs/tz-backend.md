# ТЗ: Backend

Для: backend-разработчика · см. также [контракт API](api-contract.md), [общее ТЗ MVP](mvp-spec.md), [бизнес-модель](business-model.md)

## 0. Что уже сделано (не переписывать)

В репозитории готов пакет `core/`, **источник правды для всех формул**:

| Файл | Что даёт |
| --- | --- |
| `core/parameters.py` | Реестр допущений `Params`, `registry()` для `/params`, константы классов (`UM`, `K_OP`, `K_TR`) |
| `core/economics.py` | `hub_cost`, `mesh_var`, `saving`, `pvz_contribution`, `baseline_cost`, `breakeven_orders`, `seller_capital_gain` |
| `core/simulation.py` | `simulate(p, seed)` — прогон двух схем с четырьмя фильтрами, `classify_zone`, `generate_orders` |
| `core/analysis.py` | `compare_schemes`, `scenarios`, `tornado`, `mutual_map`, `run_avg` |
| `data/seed.py` | Синтетика (`python -m data.seed`): города, ПВЗ, продавцы, SKU, заказы |
| `tests/` | 26 тестов на контрольные числа, `pytest -q` зелёный |
| `reports/results.json` | Готовые результаты модели для `/compare` и экрана «Модель» |

**Главное правило: никаких собственных формул в API.** Любая сумма берётся из `core.economics`. Если нужной функции нет, она
добавляется в `core/` с тестом, а не пишется в обработчике. Так цифры в интерфейсе, отчёте и презентации не расходятся.

**Стек:** Python 3.11, FastAPI, Pydantic, SQLAlchemy, PostgreSQL (SQLite в тестах), Docker Compose. Если команда выбрала другой стек, контракт API остаётся тем же.

---

## 1. Задачи и приёмка

Приоритеты: **P0** — без этого нет демо, **P1** — нужно для финала, **P2** — если останется время.

### T1 (P0). Каркас и Docker — ночью, ≈ 40 мин
- `api/main.py` на FastAPI, `GET /health`.
- `docker-compose.yml`: сервисы `db` (postgres), `api`, `ui` (ui делает frontend).
- `.env.example`, `Makefile` (`make up`, `make test`, `make seed`).
- Подключение к БД, миграции (Alembic) или `create_all` на старте.

**Приёмка:** `docker compose up --build` поднимает API, `/docs` открывается.

### T2 (P0). «Бесплатные» эндпоинты на готовом `core/` — ночью, ≈ 30 мин
Это самые быстрые победы: frontend сразу получает данные.

| Эндпоинт | Реализация |
| --- | --- |
| `GET /params` | `core.parameters.registry()` |
| `GET /compare` | `core.analysis.compare_schemes(Params())`, кеш на старте |
| `POST /simulate` | `run_avg(replace(Params(), **overrides))`; разрешены только поля `Params`, иначе 422 |
| `GET /model/sensitivity` · `/scenarios` · `/map` | читать `reports/results.json` |
| `GET /pvz` | из БД |

**Приёмка:** `GET /compare` возвращает те же числа, что `reports/model_report.md` (экономия 67 607 ₽/мес, 13,5%).

### T3 (P0). Модель данных и сид — ночью, ≈ 1 ч
Таблицы и поля — раздел 4 [общего ТЗ](mvp-spec.md#4-модель-данных). Минимум: `pvz`, `seller`, `sku`, `batch`, `order`, `trip`, `trip_order`, `ledger_entry`, `event_log`, `alert`.
- Загрузка `data/entities.json` в БД: `make seed`.
- Модельные часы хранятся в БД (`clock.now_h`), `POST /time/advance` двигает их.
- Остаток ведётся двумя числами: `qty` (физический) и `qty_free` (физический минус резерв). Отрицательным он быть не может (CHECK).

**Приёмка:** после `make seed` в БД 4 ПВЗ, 10 продавцов, 40 SKU.

### T4 (P0). Решатель заказа — утро, ≈ 1,5 ч
Файл `core/solver.py` (чистая функция, без БД) + тесты. Контракт ответа — поле `filters` из [API](api-contract.md#3-заказы).

```python
def solve_order(p: Params, order: OrderInput, ctx: Context) -> Decision:
    """
    order: sku_class, buyer_pvz_id, distance_km, t_h
    ctx:   zone_lambda_per_day, buyer_pvz_has_stock, pvz_free_um, next_departure_h,
           expected_trip_saving (прогноз по очереди заказов)
    """
    filters = []
    # режим A: товар уже в ПВЗ покупателя
    if ctx.buyer_pvz_has_stock and fits(order, ctx):          -> mode A
    # режим B: все фильтры
    distance   = distance_km <= 300
    zone       = classify_zone(p, ctx.zone_lambda_per_day, avg_saving) in {"GREEN","YELLOW"}
    size       = order.sku_class in MESH_ELIGIBLE
    space      = ctx.pvz_free_um >= UM[order.sku_class]
    wait_h     = ctx.next_departure_h - order.t_h
    eta_mesh   = wait_h + p.eta_leg_h
    time_ok    = eta_mesh <= p.eta_hub_h + p.delta_t_h
    price_ok   = True            # цена покупателя в обеих схемах одинакова
    trip_ok    = ctx.expected_trip_saving >= p.trip_cost (или >= p.along_cost для YELLOW)
    mode = "B" if all(...) else "C"
    return Decision(mode, eta_mesh, p.eta_hub_h, cost_mesh, cost_hub, filters)
```

**Приёмка (тесты `tests/test_solver.py`):**
| Вход | Ожидаемый результат |
| --- | --- |
| Класс `S`, зона GREEN, место есть, срок ок, рейс окупается | `B`, все `filters[*].ok = true` |
| Класс `L` или `KGT` | `C`, провален `size` |
| Зона `RED` (λ < порога) | `C`, провалена `zone` |
| `eta_mesh` больше срока хаба | `C`, провален `time` |
| Нет места в ПВЗ | `C`, провалено `space` |
| Рейс не окупается | `C`, провален `trip` |
| Дальше 300 км | `C`, провалена `distance` |
| Товар лежит в ПВЗ покупателя | `A`, перевозки нет, `eta = 4 ч` |

### T5 (P0). Приёмка, заказ, сборка, выдача — утро, ≈ 2 ч
Эндпоинты: `POST /batches`, `GET /pvz/{id}/stock`, `POST /orders`, `GET /orders/{id}`, `POST /orders/{id}/pick`, `/issue`.
- `POST /orders` вызывает `solve_order`, сохраняет `decision_json`, резервирует остаток, пишет статус.
- Переходы статусов проверяются таблицей допустимых переходов (`409 BAD_TRANSITION`).
- Каждое изменяющее действие записывается в `event_log` с `Idempotency-Key`.

**Приёмка:** сценарий 1 из раздела 3 проходит через API.

### T6 (P0). Ledger с идемпотентностью — утро, ≈ 1,5 ч
Файл `core/ledger.py` (чистая логика) + таблица `ledger_entry`.

| Событие | Проводка (дебет → кредит) | Сумма |
| --- | --- | --- |
| Приёмка | `marketplace → pvz:{id}` | `10 ₽ × k_оп × pvz_fee_scale` |
| Хранение, за день | `marketplace → pvz:{id}` | `3 ₽ × УМ` |
| Хранение продавцом, с 4-го дня | `seller:{id} → marketplace` | дни 4–7: 3 ₽/УМ·день, 8–14: 6, 15+: 10 |
| Сборка | `marketplace → pvz:{id}` | `21 ₽ × k_оп` |
| Возврат | сторно сборки | `−21 ₽ × k_оп` |
| Штраф ПВЗ | `pvz:{id} → marketplace` | по акту |

**Идемпотентность:** `UNIQUE(idempotency_key)` в `ledger_entry` и `event_log`. Повтор запроса возвращает прежний ответ без новой записи.
**Инвариант:** для каждого заказа `SUM(amount) = 0` по всем счетам.

**Приёмка (`tests/test_ledger.py`):** сумма по заказу равна 0; повтор события не создаёт запись; возврат сторнирует сборку.

### T7 (P0). Рейсы — утро, ≈ 1,5 ч
`POST /trips/plan`, `/depart`, `/arrive`, `/fail`.
- `plan` группирует заказы `B` по ближайшему отправлению и **перебирает варианты** (только попутный, выделенный, оба, ничего) по чистой экономии — это уже реализовано в `core/simulation.py` (блок «перебираем варианты рейса»), **вынести в функцию `plan_trip(p, orders, zone)` в `core/` и использовать и там, и здесь**.
- Если рейс не окупается, заказы получают `mode = C`, `reason = TRIP_NOT_PAYING`.
- `fail` пересчитывает заказы: остаются в `B` в следующем рейсе, если срок не хуже хаба, иначе `C`.

**Приёмка:** сценарии 1 и 4.

### T8 (P1). Аналитика — утро/день, ≈ 1,5 ч
- `GET /analytics/pvz/{id}`: выручка = сумма проводок `pvz:{id}`; затраты = труд (`LABOR_MIN × labor_rate_hour / 60`) + место; вклад = выручка − затраты. Использовать `core.economics.pvz_contribution` для проверки.
- `GET /analytics/seller/{id}`: по каждому заказу маржа по формуле из контракта; `commission = price × seller_commission`, `logistics_fee = seller_logistics_fee × k_тр`.

**Приёмка:** вклад ПВЗ по заказу класса S = 15 ₽ при сроке хранения 3 дня.

### T9 (P1). Возврат и долгое хранение — день, ≈ 1 ч
- `POST /orders/{id}/return` и обратный поток.
- Ежедневная задача по модельным часам: алерт `NO_SALES_D7`, `REMOVAL_D15`, начисления за хранение, блокировка пополнения.

**Приёмка:** сценарии 3 и 5.

### T10 (P2). Подсказка «в какой ПВЗ нести»
`GET /seller/{id}/recommend-pvz?sku_id=` → топ-3 по баллу `спрос − стоимость доставки до ПВЗ − штраф за загрузку − риск залёживания`. Только если всё остальное готово.

---

## 2. Тесты и сдача

- `make test` — зелёный: `tests/test_economics.py`, `test_simulation.py` (уже есть), `test_solver.py`, `test_ledger.py`, `test_scenarios.py` (пять сценариев через API на тестовой БД).
- Покрытие обязательно для: решателя, ledger, переходов статусов.
- Swagger должен содержать примеры запросов из [контракта](api-contract.md).
- В репозитории нет секретов; настройки через `.env`.

---

## 3. Пять сценариев: последовательность вызовов и ожидаемые числа

Используются как интеграционные тесты и как инструкция воспроизведения для жюри.

**Сценарий 1 — городской заказ (mesh)**
1. `POST /batches` — партия 100 ед. класса S в ПВЗ-1 (город А).
2. `POST /orders` с `buyer_pvz_id = 3` (город Б, зона GREEN) → `mode = B`, `cost_mesh` меньше `cost_hub = 109`.
3. Набрать в тот же рейс ≥ 66 заказов (прогнать генератор), `POST /trips/plan` → `kind = DEDICATED`, `net > 0`.
4. `/pick`, `/depart`, `/arrive`, `/issue`.
5. Проверить: ПВЗ-1 получил `10 + 9 + 21 = 40 ₽`, срок ≤ 48 ч, сумма ledger по заказу = 0.

**Сценарий 2 — хаб и магистраль**
1. `POST /orders` с покупателем в другом регионе (расстояние > 300 км) → `mode = C`, провален фильтр `distance`.
2. Стоимость = `hub_cost + trunk_stub` (120 ₽), mesh-проводок нет.

**Сценарий 3 — возврат**
1. Выдать заказ (`/issue`), затем `POST /orders/{id}/return`.
2. Проверить: сторно сборки (−21 ₽), отдельная плата за хранение возврата, ledger по заказу = 0.
3. Повторить запрос возврата с тем же `Idempotency-Key` → новых проводок нет.

**Сценарий 4 — ошибка в логистике**
1. Рейс с 100 заказами, `POST /trips/{id}/fail {"reason": "COURIER_NO_SHOW"}`.
2. Заказы, которые успевают в следующий рейс без потери срока, остаются `B`, остальные уходят в `C`.
3. Вариант: заявленный `S` оказался `L` при приёмке → пересчёт класса, заказ `C`, тариф пересчитан.
4. Повторное событие не дублирует начисления.

**Сценарий 5 — долгое хранение**
1. Партия 12 ед. `S`, продаж нет. `POST /time/advance {"hours": 168}` (7 дней) → алерт `NO_SALES_D7`.
2. Продвинуть до 14 дней: продавец заплатил `4×3 + 7×6 = 54 ₽` за единицу, ПВЗ получил `14 × 3 = 42 ₽`.
3. День 15 → алерт `REMOVAL_D15`, вывоз ближайшим рейсом, пополнение заблокировано.

---

## 4. Порядок работы и график

| Когда | Что |
| --- | --- |
| **Сегодня до 00:30** | T1, T2, T3. Frontend уже может работать с `/params`, `/compare`, `/simulate`, `/pvz` |
| **Утро 09:00–12:00** | T4, T5, T6, начало T7. К 09:30 нужно знать, готов ли сквозной заказ (решение по КТ-2) |
| **12:00–13:45** | T7, T8, T9, багфикс |
| **13:45** | Заморозка: только исправление блокирующих ошибок |
| **14:15–14:45** | Сдача, финальный прогон `docker compose up` с нуля |

**Если не успеваем (порядок отсечения):** T10 → автоперестроение при `fail` (оставить ручной статус) → сценарии 3–4 только в тестах, без UI → оформление.
Не отсекать: `core/`-формулы, решатель, ledger, `/compare`, README.

## 5. Чего делать не нужно

Авторизацию, платёжный шлюз, управление хабом, интеграцию с клиентским приложением, магистральную логистику (только `trunk_stub`).

## 6. Что должен уметь объяснить каждый

Жюри может спросить любого. Backend должен уметь рассказать: как решатель выбирает режим и почему именно эти четыре фильтра; откуда числа (`core/economics.py`); как устроена идемпотентность и почему сумма проводок равна нулю; что произойдёт при срыве рейса.
