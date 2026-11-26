"""Внешний контракт стадии 2: формы ответов и пять сценариев через новые маршруты."""

from decimal import Decimal

from tests.conftest import key


def _sku(client, size="S", special=False):
    for sku in client.get("/skus").json():
        if sku["size_class"] == size and sku["special"] is special:
            return sku
    raise AssertionError("нет подходящего SKU")


def _sku_at(client, pvz_id, size="S"):
    stock = client.get(f"/pvz/{pvz_id}/stock").json()
    for row in stock["batches"]:
        if row["size_class"] == size and row["qty_free"] > 0:
            return next(sku for sku in client.get("/skus").json() if sku["id"] == row["sku_id"])
    raise AssertionError(f"нет остатка класса {size} в ПВЗ {pvz_id}")


def test_params_match_contract_shape(client):
    rows = client.get("/params").json()
    first = rows[0]
    assert first.keys() == {"id", "name", "value", "unit", "note", "kind"}
    assert first["id"] == "A01"
    ids = {row["id"] for row in rows}
    assert {"A01", "A24", "A41", "A47"} <= ids


def test_time_advance_returns_model_hours(client):
    result = client.post("/time/advance", json={"hours": 24}, headers=key("advance-24"))
    assert result.status_code == 200
    body = result.json()
    assert body["now_h"] == 24.0
    assert body["now_iso"].startswith("2026-11-26T")


def test_batch_receipt_and_capacity_error(client):
    sku = _sku(client)
    payload = {"seller_id": sku["seller_id"], "sku_id": sku["id"], "pvz_id": 1, "qty": 1, "declared_class": "S"}
    receipt = client.post("/batches", json=payload, headers=key("receipt-1"))
    assert receipt.status_code == 201, receipt.text
    body = receipt.json()
    assert body["status"] == "ACCEPTED"
    assert body["um_occupied"] == 1
    assert body["ledger"][0]["type"] == "RECEIVE"
    assert sum(item["amount"] for item in body["ledger"]) == 0

    # места не хватает — ошибка CAPACITY с контекстом
    free_before = client.get("/pvz/1/stock").json()["free_um"]
    denied = client.post(
        "/batches",
        json={**payload, "qty": free_before + 1, "distribute": False},
        headers=key("receipt-2"),
    )
    assert denied.status_code == 409
    assert denied.json()["error"] == "CAPACITY"
    assert denied.json()["context"]["free_um"] == free_before


def test_batch_rejects_oversize(client):
    sku = _sku(client, "L")
    denied = client.post(
        "/batches",
        json={"seller_id": sku["seller_id"], "sku_id": sku["id"], "pvz_id": 1, "qty": 1, "declared_class": "L"},
        headers=key("oversize"),
    )
    assert denied.status_code == 409
    assert denied.json()["error"] == "SIZE_NOT_ALLOWED"


def test_stock_shape(client):
    body = client.get("/pvz/1/stock").json()
    assert set(body) >= {
        "pvz_id", "capacity_um", "available_um", "occupied_um", "free_um",
        "load_pct", "batches", "alerts",
    }
    batch = body["batches"][0]
    assert set(batch) >= {
        "batch_id", "sku_id", "seller_id", "size_class", "um",
        "qty", "qty_free", "days_stored", "alert",
    }


def test_scenario_1_city_order_full_cycle(client):
    sku = _sku_at(client, 3)
    created = client.post(
        "/orders",
        json={"sku_id": sku["id"], "buyer_pvz_id": 1, "qty": 1},
        headers=key("s1-create"),
    )
    assert created.status_code == 201, created.text
    order = created.json()
    assert order["mode"] == "B"
    assert Decimal(str(order["cost_mesh"])) == Decimal("95.00")
    assert Decimal(str(order["cost_hub"])) == Decimal("109.00")
    assert {"name", "ok", "value"} == set(order["filters"][0])
    assert all(item["ok"] for item in order["filters"])

    order_id = order["order_id"]

    planned = client.post("/trips/plan", json={"departure_h": 6}, headers=key("s1-plan"))
    assert planned.status_code == 200, planned.text
    trip = next(item for item in planned.json()["trips"] if order_id in item["order_ids"])
    assert trip["kind"] == "DEDICATED"
    assert trip["net"] > 0

    picked = client.post(f"/orders/{order_id}/pick", headers=key("s1-pick"))
    assert picked.json()["status"] == "PICKED"
    assert picked.json()["ledger"]  # сборка оплачена

    departed = client.post(f"/trips/{trip['trip_id']}/depart", headers=key("s1-depart"))
    assert departed.status_code == 200, departed.text
    arrived = client.post(f"/trips/{trip['trip_id']}/arrive", headers=key("s1-arrive"))
    assert arrived.status_code == 200, arrived.text

    issued = client.post(f"/orders/{order_id}/issue", headers=key("s1-issue"))
    assert issued.json()["status"] == "ISSUED"
    ledger = client.get("/ledger", params={"order_id": order_id}).json()
    assert Decimal(str(sum(item["amount"] for item in ledger))) == Decimal("0")

    detail = client.get(f"/orders/{order_id}").json()
    assert detail["trip_id"] == trip["trip_id"]
    statuses = [point["status"] for point in detail["timeline"]]
    assert "RESERVED" in statuses and "ISSUED" in statuses
    assert all(point["t_h"] >= 0 for point in detail["timeline"])


def test_scenario_2_far_order_trunk_stub(client):
    sku = _sku_at(client, 1)
    order = client.post(
        "/orders",
        json={"sku_id": sku["id"], "buyer_pvz_id": 5, "qty": 1},
        headers=key("s2-create"),
    ).json()
    assert order["mode"] == "C"
    assert Decimal(str(order["cost_hub"])) == Decimal("229.00")  # 109 + 120 ₽ магистраль
    failed = next(item for item in order["filters"] if item["name"] == "distance")
    assert failed["ok"] is False


def test_scenario_3_return_reverses_assemble(client):
    sku = _sku_at(client, 3)
    order_id = client.post(
        "/orders",
        json={"sku_id": sku["id"], "buyer_pvz_id": 1, "qty": 1},
        headers=key("s3-create"),
    ).json()["order_id"]
    client.post(f"/orders/{order_id}/pick", headers=key("s3-pick"))
    planned = client.post("/trips/plan", json={"departure_h": 6}, headers=key("s3-plan")).json()
    trip_id = next(t["trip_id"] for t in planned["trips"] if order_id in t["order_ids"])
    client.post(f"/trips/{trip_id}/depart", headers=key("s3-depart"))
    client.post(f"/trips/{trip_id}/arrive", headers=key("s3-arrive"))
    client.post(f"/orders/{order_id}/issue", headers=key("s3-issue"))

    first = client.post(f"/orders/{order_id}/return", headers=key("s3-ret-1"))
    assert first.json()["status"] == "RETURN_REQUESTED"
    second = client.post(f"/orders/{order_id}/return/transit", headers=key("s3-ret-2"))
    assert second.json()["status"] == "RETURN_IN_TRANSIT"
    third = client.post(f"/orders/{order_id}/return/accept", headers=key("s3-ret-3"))
    assert third.json()["status"] == "RETURNED"

    entries = client.get("/ledger", params={"order_id": order_id}).json()
    types = {item["type"] for item in entries}
    assert "ASSEMBLE" in types
    assert "RETURN_PICKING_REVERSAL" in types
    assert Decimal(str(sum(item["amount"] for item in entries))) == Decimal("0")
    repeat = client.post(f"/orders/{order_id}/return/accept", headers=key("s3-ret-3"))
    assert repeat.status_code == 200  # повтор события не меняет состояние


def test_bad_transition_and_validation(client):
    sku = _sku_at(client, 3)
    order_id = client.post(
        "/orders",
        json={"sku_id": sku["id"], "buyer_pvz_id": 1, "qty": 1},
        headers=key("bad-create"),
    ).json()["order_id"]
    denied = client.post(f"/orders/{order_id}/issue", headers=key("bad-issue"))
    assert denied.status_code == 409
    assert denied.json()["error"] == "BAD_TRANSITION"

    invalid = client.post("/orders", json={"sku_id": sku["id"]}, headers=key("bad-2"))
    assert invalid.status_code == 422
    assert invalid.json()["error"] == "VALIDATION_ERROR"
    assert invalid.json()["context"]["fields"]

    missing = client.post("/orders", json={"sku_id": sku["id"], "buyer_pvz_id": 1})
    assert missing.status_code == 400  # нет Idempotency-Key


def test_model_endpoints_read_published_report(client):
    comparison = client.get("/compare")
    assert comparison.status_code == 200, comparison.text
    data = comparison.json()
    assert {"mesh_dedicated_only", "mesh_with_along"} <= set(data)
    assert data["mesh_with_along"]["saving_month"] > 0

    for path in ("/model/sensitivity", "/model/scenarios", "/model/map"):
        response = client.get(path)
        assert response.status_code == 200, response.text

    check = client.post("/simulate", json={"overrides": {"orders_per_day": 80}}, headers=key("sim-1"))
    assert check.status_code == 200, check.text
    payload = check.json()
    assert payload["orders"] > 0 and "saving_month" in payload

    bad = client.post("/simulate", json={"overrides": {"unknown_field": 1}}, headers=key("sim-2"))
    assert bad.status_code == 422
    assert bad.json()["error"] == "VALIDATION_ERROR"
    assert "unknown_field" in bad.json()["context"]["fields"]


def test_contract_analytics_shapes(client):
    pvz = client.get("/analytics/pvz/1").json()
    assert pvz.keys() >= {"pvz_id", "period_days", "revenue", "costs", "contribution",
                          "contribution_per_um_day", "load_pct", "by_day", "before_after"}
    assert pvz["pvz_id"] == 1 and pvz["period_days"] == 30
    assert {"labor", "space"} <= set(pvz["costs"])
    if pvz["by_day"]:
        assert {"day", "revenue", "contribution"} <= set(pvz["by_day"][0])

    seller = client.get("/analytics/seller/1").json()
    assert seller.keys() == {"seller_id", "orders", "totals"}
    assert {"revenue", "margin", "storage_fee", "avg_storage_days"} <= set(seller["totals"])
    if seller["orders"]:
        order = seller["orders"][0]
        assert order.keys() == {"order_id", "price", "unit_cost", "commission",
                                "logistics_fee", "storage_fee", "return_cost", "margin"}
        expected = (order["price"] - order["unit_cost"] - order["commission"]
                    - order["logistics_fee"] - order["storage_fee"] - order["return_cost"])
        assert abs(order["margin"] - expected) < 0.02
        s_sku = next(row for row in client.get("/skus").json() if row["size_class"] == "S")
        assert order["logistics_fee"] == 60.0 if order["order_id"] else True
