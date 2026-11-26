"""Прогноз спроса по SKU и подсказка продавцу."""


def test_pvz_forecast_is_based_on_history(client):
    data = client.get("/api/forecast/pvz/1").json()
    assert data["pvz_id"] == 1
    assert data["items"], "у ПВЗ должна быть история продаж"
    top = data["items"][0]
    assert top["sold"] > 0
    assert top["forecast_units"] >= 1
    assert top["recommended"] >= 0
    assert top["reason"]


def test_forecast_does_not_recommend_more_than_shortage(client):
    data = client.get("/api/forecast/pvz/1").json()
    for item in data["items"]:
        expected = max(0, item["forecast_units"] - item["stock"] - item["incoming"])
        assert item["recommended"] <= expected


def test_seller_recommendation_top3(client):
    sku = next(row for row in client.get("/api/skus").json() if row["size_class"] == "S")
    data = client.get(
        f"/api/seller/{sku['seller_id']}/recommend-pvz", params={"sku_id": sku["id"]}
    ).json()
    assert 1 <= len(data["items"]) <= 3
    scores = [item["score"] for item in data["items"]]
    assert scores == sorted(scores, reverse=True)
    assert {"pvz_id", "demand", "free_um", "score"} <= set(data["items"][0])


def test_recommendation_rejects_foreign_sku(client):
    sku = next(row for row in client.get("/api/skus").json() if row["seller_id"] != 1)
    response = client.get(f"/api/seller/1/recommend-pvz", params={"sku_id": sku["id"]})
    assert response.status_code == 404
