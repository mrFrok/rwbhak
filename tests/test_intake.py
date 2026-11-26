"""Частичная приёмка и распределение остатка по другим ПВЗ."""

from sqlalchemy import func, select

from api.db import SessionLocal
from api.models import LedgerEntry
from tests.conftest import key


def _sku(client):
    return next(row for row in client.get("/api/skus").json() if row["size_class"] == "S")


def test_remainder_is_distributed_across_pvz(client):
    sku = _sku(client)
    before = client.get("/api/pvz/1/stock").json()
    free_target = before["space_free_um"]

    response = client.post(
        "/api/batches",
        headers=key("partial-1"),
        json={
            "seller_id": sku["seller_id"], "sku_id": sku["id"], "pvz_id": 1,
            "qty": 500, "declared_class": "S", "distribute": True,
        },
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["accepted_qty"] + result["unplaced_qty"] == 500
    assert result["unplaced_qty"] > 0
    assert result["distributed"] is True
    assert len(result["allocations"]) >= 2

    pvz_ids = [row["pvz_id"] for row in result["allocations"]]
    assert len(pvz_ids) == len(set(pvz_ids))
    assert pvz_ids[0] == 1  # сначала заполняем выбранный ПВЗ
    assert sum(row["qty"] for row in result["allocations"]) == result["accepted_qty"]

    # в выбранном ПВЗ приняли всю доступную ёмкость, но не больше
    assert result["allocations"][0]["qty"] == free_target
    after = client.get("/api/pvz/1/stock").json()
    assert after["space_free_um"] == 0

    with SessionLocal() as db:
        total = db.scalar(select(func.coalesce(func.sum(LedgerEntry.amount_kop), 0)))
    assert total == 0


def test_distribution_stays_within_one_city(client):
    sku = _sku(client)
    response = client.post(
        "/api/batches",
        headers=key("partial-2"),
        json={
            "seller_id": sku["seller_id"], "sku_id": sku["id"], "pvz_id": 1,
            "qty": 500, "declared_class": "S", "distribute": True,
        },
    ).json()
    cities = {row["city"] for row in response["allocations"]}
    pvz_ids = {row["pvz_id"] for row in response["allocations"]}
    assert cities == {"Пермь"}
    assert pvz_ids <= {1, 2, 6, 7, 9}
    assert response["unplaced_qty"] > 0


def test_full_batch_fits_single_pvz_without_distribution(client):
    sku = _sku(client)
    response = client.post(
        "/api/batches",
        headers=key("partial-3"),
        json={
            "seller_id": sku["seller_id"], "sku_id": sku["id"], "pvz_id": 1,
            "qty": 1, "declared_class": "S", "distribute": True,
        },
    ).json()
    assert response["accepted_qty"] == 1
    assert response["unplaced_qty"] == 0
    assert response["distributed"] is False
    assert len(response["allocations"]) == 1


def test_without_distribute_still_rejects_oversized_batch(client):
    sku = _sku(client)
    response = client.post(
        "/api/batches",
        headers=key("partial-4"),
        json={
            "seller_id": sku["seller_id"], "sku_id": sku["id"], "pvz_id": 1,
            "qty": 500, "declared_class": "S",
        },
    )
    assert response.status_code == 409
    assert "места" in response.json()["detail"]
