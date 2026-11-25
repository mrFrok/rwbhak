"""Сквозные сценарии через API."""

from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor

from tests.conftest import key


def _sku(client, size="S", special=False):
    for sku in client.get("/api/skus").json():
        if sku["size_class"] == size and sku["special"] is special:
            return sku
    raise AssertionError("нет подходящего SKU")


def _order(client, name, **payload):
    response = client.post("/api/orders", json=payload, headers=key(name))
    assert response.status_code == 201, response.text
    return response.json()


def test_health_and_params(client):
    assert client.get("/api/health").json()["status"] == "ok"
    data = client.get("/api/params").json()
    assert any(item["code"] == "trip.dedicated" for item in data["assumptions"])
    assert all("source" in item for item in data["assumptions"])


def test_city_order_mode_b_at_95_rubles(client):
    sku = _sku(client)
    order = _order(client, "b", sku_id=sku["id"], buyer_pvz_id=1, source_pvz_id=3)
    assert order["mode"] == "B"
    assert order["trip_id"] == 1
    assert order["status"] == "RESERVED"
    assert Decimal(str(order["cost_mesh"])) == Decimal("95.00")
    assert Decimal(str(order["cost_hub"])) == Decimal("109.00")
    assert all(item["ok"] for item in order["decision"]["filters"])


def test_receive_batch_reserve_and_issue(client):
    sku = _sku(client)
    stock = client.get("/api/pvz/1/stock").json()
    received = client.post(
        "/api/batches", headers=key("receive"),
        json={"sku_id": sku["id"], "pvz_id": 1, "qty": 1, "declared_class": "S"},
    )
    assert received.status_code == 201, received.text
    batch = received.json()
    assert batch["space_free_after_um"] == stock["space_free_um"] - 1

    order = _order(client, "from-new-batch", sku_id=sku["id"], buyer_pvz_id=1, batch_id=batch["id"])
    issue = client.post(f"/api/orders/{order['id']}/issue", headers=key("issue-new-batch"))
    assert issue.status_code == 200, issue.text
    after = client.get("/api/pvz/1/stock").json()
    assert after["space_free_um"] == stock["space_free_um"]
    assert next(row for row in after["batches"] if row["id"] == batch["id"])["qty"] == 0


def test_only_one_request_can_reserve_last_item(client):
    sku = _sku(client)
    batch = client.post(
        "/api/batches", headers=key("single-unit"),
        json={"sku_id": sku["id"], "pvz_id": 1, "qty": 1, "declared_class": "S"},
    ).json()

    def reserve(index):
        return client.post(
            "/api/orders", headers=key(f"reserve-{index}"),
            json={"sku_id": sku["id"], "buyer_pvz_id": 1, "batch_id": batch["id"]},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reserve, range(2))) == [201, 409]


def test_mode_a_from_shelf(client):
    sku = _sku(client)
    order = _order(client, "a", sku_id=sku["id"], buyer_pvz_id=1, source_pvz_id=1)
    assert order["mode"] == "A"
    assert order["eta_mesh_h"] <= 4


def test_far_order_goes_through_hub(client):
    sku = _sku(client)
    order = _order(client, "far", sku_id=sku["id"], buyer_pvz_id=5, source_pvz_id=3)
    assert order["mode"] == "C"
    assert "distance" in order["decision"]["blocked_by"]


def test_small_along_trip_is_not_paid(client):
    sku = _sku(client)
    order = _order(client, "small", sku_id=sku["id"], buyer_pvz_id=2, source_pvz_id=4)
    assert order["mode"] == "C"
    assert "trip" in order["decision"]["blocked_by"]
    assert client.post("/api/trips/2/depart", headers=key("small-depart")).status_code == 409


def test_list_trips_and_fallback_after_failure(client):
    assert len(client.get("/api/trips").json()) == 2
    sku = _sku(client)
    order = _order(client, "before-failure", sku_id=sku["id"], buyer_pvz_id=1, source_pvz_id=3)
    response = client.post("/api/trips/1/fail", headers=key("fail"))
    assert response.status_code == 200, response.text
    assert response.json()["rerouted"]["to_hub"] == 100
    updated = client.get(f"/api/orders/{order['id']}").json()
    assert updated["mode"] == "C"
    assert updated["status"] == "ROUTED_HUB"
    assert updated["trip_id"] is None


def test_full_cycle_b_and_ledger_balances(client):
    sku = _sku(client)
    order = _order(client, "full", sku_id=sku["id"], buyer_pvz_id=1, source_pvz_id=3)
    oid = order["id"]

    picked = client.post(f"/api/orders/{oid}/pick", headers=key("pick"))
    assert picked.status_code == 200, picked.text
    assert picked.json()["status"] == "PICKED"

    departed = client.post("/api/trips/1/depart", headers=key("depart"))
    assert departed.status_code == 200, departed.text
    assert departed.json()["status"] == "IN_TRANSIT"

    arrived = client.post("/api/trips/1/arrive", headers=key("arrive"))
    assert arrived.status_code == 200, arrived.text
    assert arrived.json()["status"] == "ARRIVED"

    issued = client.post(f"/api/orders/{oid}/issue", headers=key("issue"))
    assert issued.status_code == 200, issued.text
    assert issued.json()["status"] == "ISSUED"

    ledger = client.get(f"/api/orders/{oid}/ledger").json()
    assert Decimal(str(ledger["balance"])) == Decimal("0")
    assert any(entry["type"] == "ON_TIME_BONUS" for entry in ledger["entries"])


def test_return_three_stages(client):
    sku = _sku(client)
    order = _order(client, "ret", sku_id=sku["id"], buyer_pvz_id=1, source_pvz_id=1)
    oid = order["id"]
    assert client.post(f"/api/orders/{oid}/issue", headers=key("ret-issue")).status_code == 200
    first = client.post(f"/api/orders/{oid}/return", headers=key("ret-1"))
    assert first.json()["status"] == "RETURN_REQUESTED"
    second = client.post(f"/api/orders/{oid}/return/transit", headers=key("ret-2"))
    assert second.json()["status"] == "RETURN_IN_TRANSIT"
    third = client.post(f"/api/orders/{oid}/return/accept", headers=key("ret-3"))
    assert third.json()["status"] == "RETURNED"
    ledger = client.get(f"/api/orders/{oid}/ledger").json()
    assert Decimal(str(ledger["balance"])) == Decimal("0")
    # Режим A: сборки не было, но бонус за выдачу сторнируется, продавец платит возврат.
    kinds = {entry["type"] for entry in ledger["entries"]}
    assert "RETURN_BONUS_REVERSAL" in kinds
    assert "RETURN_LOGISTICS" in kinds
    assert "RETURN_PICKING_REVERSAL" not in kinds
    repeat = client.post(f"/api/orders/{oid}/return/accept", headers=key("ret-3"))
    assert repeat.json() == third.json()
    assert client.get(f"/api/orders/{oid}/ledger").json() == ledger


def test_long_storage_alerts_and_blocks_replenishment(client):
    sku = _sku(client)
    response = client.post(
        "/api/batches", headers=key("keep-stock"),
        json={"sku_id": sku["id"], "pvz_id": 5, "qty": 1, "declared_class": "S"},
    )
    assert response.status_code == 201, response.text
    batch_id = response.json()["id"]

    for step, expected in ((7, "NO_SALES_D7"), (8, "REMOVAL_D15")):
        assert client.post("/api/time/advance", headers=key(f"advance-{step}"), json={"days": step}).is_success
        alerts = client.get("/api/pvz/5/alerts").json()
        assert any(row["batch_id"] == batch_id and row["type"] == expected for row in alerts)
    blocked = client.post(
        "/api/batches", headers=key("restock"),
        json={"sku_id": sku["id"], "pvz_id": 5, "qty": 1, "declared_class": "S"},
    )
    assert blocked.status_code == 409


def test_idempotency_replays_and_conflicts(client):
    sku = _sku(client)
    payload = {"sku_id": sku["id"], "buyer_pvz_id": 1, "source_pvz_id": 3}
    first = client.post("/api/orders", json=payload, headers=key("idem"))
    second = client.post("/api/orders", json=payload, headers=key("idem"))
    assert first.json()["id"] == second.json()["id"]

    conflict = client.post(
        "/api/orders",
        json={**payload, "buyer_pvz_id": 2},
        headers=key("idem"),
    )
    assert conflict.status_code == 409


def test_missing_idempotency_key(client):
    sku = _sku(client)
    response = client.post("/api/orders", json={"sku_id": sku["id"], "buyer_pvz_id": 1})
    assert response.status_code == 400


def test_batch_capacity_limit(client):
    sku = _sku(client, "M")
    response = client.post(
        "/api/batches",
        json={"sku_id": sku["id"], "pvz_id": 1, "qty": 500, "declared_class": "M"},
        headers=key("batch-big"),
    )
    assert response.status_code == 409
    assert "места" in response.json()["detail"]


def test_compare_and_threshold(client):
    data = client.get("/api/compare").json()
    assert data["flow_orders"] == 3000
    assert data["totals"]["saving"] > 0
    assert data["mesh"]["orders"] > 0

    threshold = client.get("/api/threshold").json()
    assert threshold["threshold"] == 77
    assert threshold["points"][-1]["mesh"] < threshold["points"][0]["mesh"]


def test_pvz_analytics_has_revenue(client):
    data = client.get("/api/analytics/pvz/1").json()
    assert data["revenue"] > 0
    assert "contribution" in data
    assert data["stock"]["pvz"]["capacity_um"] == 200


def test_seller_analytics_has_full_margin(client):
    data = client.get("/api/analytics/seller/1").json()
    assert "orders" in data
    assert data["totals"]["margin"] != 0
    assert "margin_pct" in data["totals"]
    assert "15%" in data["note"]
    order = data["orders"][0]
    for field in ("commission", "acquiring", "logistics", "storage", "returns", "tax", "margin"):
        assert field in order
