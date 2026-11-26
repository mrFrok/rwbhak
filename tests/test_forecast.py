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


def test_seller_has_home_city(client):
    seller = client.get("/api/sellers").json()[0]
    assert seller["city"] == "Пермь"
    assert seller["city_id"] == 1


def test_recommendations_respect_seller_geography(client):
    seller = next(row for row in client.get("/api/sellers").json() if row["city"] == "Пермь")
    sku = next(
        row for row in client.get("/api/skus").json() if row["seller_id"] == seller["id"]
    )
    data = client.get(
        f"/api/seller/{seller['id']}/recommend-pvz", params={"sku_id": sku["id"]}
    ).json()
    assert data["seller_city"] == "Пермь"
    cities = {item["city"] for item in data["items"]}
    assert "Москва" not in cities
    assert cities <= {"Пермь", "Соликамск"}


def test_forecast_ignores_far_demand(client):
    # В Москву идут только дальние заказы (режим C), локального спроса нет.
    data = client.get("/api/forecast/pvz/5").json()
    assert data["items"] == []
