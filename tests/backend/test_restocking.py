"""
Tests for restocking recommendation and order endpoints.
"""
import pytest


def recommend(client, budget):
    response = client.get("/api/restocking/recommendations", params={"budget": budget})
    assert response.status_code == 200
    return response.json()


class TestRecommendations:
    def test_zero_budget_recommends_nothing(self, client):
        data = recommend(client, 0)
        assert data["items"] == []
        assert data["total_cost"] == 0
        assert data["remaining_budget"] == 0

    def test_negative_budget_rejected(self, client):
        response = client.get("/api/restocking/recommendations", params={"budget": -1})
        assert response.status_code == 400

    def test_never_exceeds_budget(self, client):
        for budget in (100, 1000, 5000, 20000, 50000):
            data = recommend(client, budget)
            assert data["total_cost"] <= budget
            assert data["remaining_budget"] >= 0

    def test_small_budget_partially_fills_top_priority_item(self, client):
        data = recommend(client, 1000)
        assert len(data["items"]) >= 1
        first = data["items"][0]
        # The top item could not be fully covered, so it is a partial buy
        assert 0 < first["quantity"] < first["shortfall"]

    def test_large_budget_covers_all_but_decreasing_items(self, client):
        full = recommend(client, 0)["full_cost"]
        data = recommend(client, full + 1)
        skus = {i["sku"] for i in data["items"]}
        assert "MTR-304" not in skus  # decreasing trend is never recommended
        assert all(i["quantity"] == i["shortfall"] for i in data["items"])
        assert data["total_cost"] == pytest.approx(full)

    def test_increasing_items_ranked_before_stable(self, client):
        trends = [i["trend"] for i in recommend(client, 1_000_000)["items"]]
        assert trends == sorted(trends, key=lambda t: t != "increasing")

    def test_stock_on_hand_reduces_shortfall(self, client):
        # PSU-501 forecasts 252 and has 420 in inventory, so no shortfall
        skus = {i["sku"] for i in recommend(client, 1_000_000)["items"]}
        assert "PSU-501" not in skus


class TestCreateOrder:
    def test_create_order(self, client):
        response = client.post("/api/restocking-orders", json={
            "items": [{"sku": "WDG-001", "quantity": 10}, {"sku": "MTR-304", "quantity": 2}]
        })
        assert response.status_code == 201
        order = response.json()
        assert order["status"] == "Submitted"
        assert order["order_number"].startswith("RST-")
        # Totals and lead time are computed server-side: 10*42.50 + 2*310.00; slowest item is MTR-304 (21d)
        assert order["total_cost"] == pytest.approx(1045.0)
        assert order["lead_time_days"] == 21
        assert order["expected_delivery"] > order["submitted_date"]

    def test_client_cannot_set_price(self, client):
        response = client.post("/api/restocking-orders", json={
            "items": [{"sku": "WDG-001", "quantity": 1, "unit_cost": 0.01}]
        })
        assert response.json()["total_cost"] == pytest.approx(42.5)

    @pytest.mark.parametrize("items", [
        [],
        [{"sku": "NOPE-999", "quantity": 1}],
        [{"sku": "WDG-001", "quantity": 0}],
        [{"sku": "WDG-001", "quantity": -5}],
    ])
    def test_invalid_orders_rejected(self, client, items):
        response = client.post("/api/restocking-orders", json={"items": items})
        assert response.status_code == 400

    def test_list_orders_newest_first(self, client):
        assert client.get("/api/restocking-orders").json() == []
        for sku in ("WDG-001", "BRG-102"):
            client.post("/api/restocking-orders", json={"items": [{"sku": sku, "quantity": 1}]})
        orders = client.get("/api/restocking-orders").json()
        assert [o["items"][0]["sku"] for o in orders] == ["BRG-102", "WDG-001"]
