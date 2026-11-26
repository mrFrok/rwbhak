# Контракт API

Единый документ для backend и frontend: по нему они работают параллельно. Backend реализует,
frontend сначала подключается к заглушкам с теми же JSON (см. [ТЗ frontend](tz-frontend.md)).
Если контракт нужно изменить, правка вносится **здесь** и сообщается обоим.

**Общие правила**

- База: `http://localhost:8000`, документация Swagger: `/docs`.
- Формат: JSON, деньги в рублях (`float`, 2 знака), время в модельных часах от начала периода (`t_h`) и ISO-датах.
- Все изменяющие запросы (`POST`) принимают заголовок `Idempotency-Key`. Повтор с тем же ключом возвращает прежний ответ и **не** создаёт новых проводок.
- Ошибка: `{"error": "CAPACITY", "detail": "…", "context": {…}}`, коды HTTP: 400 (данные), 404, 409 (конфликт состояния), 422 (валидация).
- Все числа считает `core/` (`core.economics`, `core.simulation`). Backend ничего не пересчитывает по-своему.

**Классы габаритов:** `S`, `M`, `L`, `KGT`. **Режимы:** `A` (с полки), `B` (рейс ПВЗ → ПВЗ), `C` (хаб).

---

## 1. Справочные

### `GET /params`
Реестр допущений (`core.parameters.registry()`).
```json
[{"id": "A01", "name": "hub_proc", "value": 25.0, "unit": "₽",
  "note": "Обработка на хабе × k_оп", "kind": "допущение команды"}]
```

### `GET /pvz`
```json
[{"id": 1, "name": "ПВЗ-1", "city_id": 1, "capacity_um": 200, "available_um": 170}]
```

### `POST /time/advance`
Перевод модельных часов (нужен для сценариев хранения и рейсов).
```json
{"hours": 24}   →   {"now_h": 96.0, "now_iso": "2026-11-29T08:00:00"}
```

---

## 2. Приёмка и остатки

### `POST /batches` — приёмка партии в ПВЗ
```json
{"seller_id": 3, "sku_id": 12, "pvz_id": 1, "qty": 20, "declared_class": "S"}
```
Ответ `201`:
```json
{"batch_id": 55, "status": "ACCEPTED", "qty": 20, "um_occupied": 20,
 "free_um_after": 118, "ledger": [{"account": "pvz:1", "type": "RECEIVE", "amount": 200.0}]}
```
Ответ `409` при нехватке места: `{"error": "CAPACITY", "context": {"free_um": 12, "needed_um": 20}}`.
Для классов `L` и `KGT` приём в mesh возвращает `409 {"error": "SIZE_NOT_ALLOWED"}`.

### `GET /pvz/{id}/stock`
```json
{"pvz_id": 1, "capacity_um": 200, "available_um": 170, "occupied_um": 52, "free_um": 118,
 "load_pct": 30.6,
 "batches": [{"batch_id": 55, "sku_id": 12, "seller_id": 3, "size_class": "S", "um": 1,
              "qty": 20, "qty_free": 18, "days_stored": 3, "alert": null}],
 "alerts": [{"batch_id": 41, "type": "NO_SALES_D7", "days_stored": 7}]}
```
`alert`: `null`, `NO_SALES_D7`, `REMOVAL_D15`, `CAPACITY`.

---

## 3. Заказы

### `POST /orders` — создание заказа и решение
```json
{"sku_id": 12, "buyer_pvz_id": 3, "qty": 1}
```
Ответ `201`:
```json
{
  "order_id": 901,
  "status": "RESERVED",
  "mode": "B",
  "eta_mesh_h": 35.0,
  "eta_hub_h": 48.0,
  "cost_mesh": 95.0,
  "cost_hub": 109.0,
  "filters": [
    {"name": "distance", "ok": true,  "value": "120 км ≤ 300"},
    {"name": "zone",     "ok": true,  "value": "GREEN, λ = 74 зак/день"},
    {"name": "size",     "ok": true,  "value": "S"},
    {"name": "space",    "ok": true,  "value": "free_um = 118"},
    {"name": "time",     "ok": true,  "value": "35 ч ≤ 48 ч"},
    {"name": "price",    "ok": true,  "value": "цена покупателя не меняется"},
    {"name": "trip",     "ok": true,  "value": "прогноз экономии рейса 5 900 ₽ ≥ 4 500 ₽"}
  ]
}
```
Если фильтр не пройден: `mode: "C"`, у фильтра `ok: false`, `status: "ROUTED_HUB"`.
Режим `B` на момент создания **предварительный**: окончательно он подтверждается при `POST /trips/plan`.

### `GET /orders/{id}`
Тот же объект + `status`, `trip_id`, `timeline: [{"status": "RESERVED", "t_h": 70.5}]`.

### `POST /orders/{id}/pick` · `POST /orders/{id}/issue` · `POST /orders/{id}/return`
```json
{"order_id": 901, "status": "PICKED", "ledger": [{"account": "pvz:1", "type": "ASSEMBLE", "amount": 21.0}]}
```
Допустимые переходы статусов: `RESERVED → PICKED → IN_TRIP → ARRIVED → ISSUED`, режим A: `PICKED → ISSUED`,
`ISSUED → RETURN_REQUESTED → RETURN_IN_TRANSIT → RETURNED`. Недопустимый переход: `409 {"error": "BAD_TRANSITION"}`.

---

## 4. Рейсы

### `POST /trips/plan` — сформировать рейсы из накопленных заказов
```json
{"departure_h": 80.0}
```
Ответ:
```json
{"trips": [{"trip_id": 7, "kind": "DEDICATED", "order_ids": [901, 902], "um": 171,
            "cost": 4500.0, "saving": 7224.0, "net": 2724.0}],
 "rerouted": [{"order_id": 905, "reason": "TRIP_NOT_PAYING", "mode": "C"},
              {"order_id": 906, "reason": "TIME", "mode": "C"}]}
```
`kind`: `DEDICATED` или `ALONG`. Причины перенаправления: `TRIP_NOT_PAYING`, `TIME`, `CAPACITY`, `SIZE`.

### `POST /trips/{id}/depart` · `/arrive`
Меняют статусы заказов рейса (`IN_TRIP`, `ARRIVED`) и пишут проводки.

### `POST /trips/{id}/fail`
```json
{"reason": "COURIER_NO_SHOW"}
```
Ответ: пересчёт заказов рейса:
```json
{"trip_id": 7, "rerouted": [{"order_id": 901, "new_mode": "B", "new_trip_id": 8, "new_eta_h": 41.0},
                            {"order_id": 902, "new_mode": "C", "reason": "TIME"}]}
```

---

## 5. Аналитика и модель

### `GET /analytics/pvz/{id}?days=30`
```json
{"pvz_id": 1, "period_days": 30,
 "revenue": 12400.0, "costs": {"labor": 6200.0, "space": 1550.0},
 "contribution": 4650.0, "contribution_per_um_day": 4.8, "load_pct": 31.0,
 "by_day": [{"day": 1, "revenue": 410.0, "contribution": 150.0}],
 "before_after": {"before": 0.0, "after": 4650.0}}
```

### `GET /analytics/seller/{id}?days=30`
```json
{"seller_id": 3,
 "orders": [{"order_id": 901, "price": 1200.0, "unit_cost": 650.0, "commission": 180.0,
             "logistics_fee": 60.0, "storage_fee": 0.0, "return_cost": 0.0, "margin": 310.0}],
 "totals": {"revenue": 24000.0, "margin": 6200.0, "storage_fee": 120.0, "avg_storage_days": 3.1}}
```
Формула маржи: `price − unit_cost − commission − logistics_fee − storage_fee − return_cost`.

### `GET /compare`
Возвращает `core.analysis.compare_schemes(Params())` (хаб, mesh только выделенные, mesh с попутными).
Готовый пример в `reports/results.json` → ключ `comparison`.

### `POST /simulate`
```json
{"overrides": {"orders_per_day": 80, "trip_cost_scale": 1.2}}
```
Возвращает метрики `core.analysis.run_avg(replace(Params(), **overrides))`.

### `GET /model/sensitivity`, `GET /model/scenarios`, `GET /model/map`
Отдают `tornado_marketplace`, `scenarios`, `mutual_map` из `reports/results.json` (пересчёт по `POST /simulate`).

---

## 6. Ledger

### `GET /ledger?order_id=901`
```json
[{"id": 1, "account": "pvz:1", "type": "RECEIVE", "amount": 10.0, "order_id": 901,
  "idempotency_key": "batch-55-receive"}]
```
Правило: сумма проводок по заказу равна нулю (каждая проводка имеет парную с обратным знаком на счёте `marketplace`).
