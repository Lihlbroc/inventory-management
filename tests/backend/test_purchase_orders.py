"""
Tests for purchase order API endpoints.
"""
import pytest

import main


@pytest.fixture(autouse=True)
def clean_purchase_orders():
    """Purchase orders live in module-level memory, so restore them around every test."""
    original = list(main.purchase_orders)
    original_counter = main._next_po_number
    yield
    main.purchase_orders[:] = original
    main._next_po_number = original_counter


@pytest.fixture
def backlog_item_id():
    """A backlog item id that exists in the mock data."""
    return main.backlog_items[0]["id"]


def po_payload(backlog_item_id, **overrides):
    payload = {
        "backlog_item_id": backlog_item_id,
        "supplier_name": "Acme Components",
        "quantity": 350,
        "unit_cost": 12.5,
        "expected_delivery_date": "2025-12-01",
        "notes": "Rush order",
    }
    payload.update(overrides)
    return payload


class TestCreatePurchaseOrder:
    """Test suite for POST /api/purchase-orders."""

    def test_create_purchase_order(self, client, backlog_item_id):
        response = client.post("/api/purchase-orders", json=po_payload(backlog_item_id))
        assert response.status_code == 201

        po = response.json()
        assert po["id"].startswith("PO-")
        assert po["backlog_item_id"] == backlog_item_id
        assert po["supplier_name"] == "Acme Components"
        assert po["quantity"] == 350
        assert po["unit_cost"] == 12.5
        assert po["expected_delivery_date"] == "2025-12-01"
        assert po["status"] == "Pending"
        assert po["notes"] == "Rush order"
        assert po["created_date"]

    def test_notes_are_optional(self, client, backlog_item_id):
        payload = po_payload(backlog_item_id)
        del payload["notes"]
        response = client.post("/api/purchase-orders", json=payload)
        assert response.status_code == 201
        assert response.json()["notes"] is None

    def test_ids_are_unique(self, client):
        first_id, second_id = main.backlog_items[0]["id"], main.backlog_items[1]["id"]
        a = client.post("/api/purchase-orders", json=po_payload(first_id)).json()
        b = client.post("/api/purchase-orders", json=po_payload(second_id)).json()
        assert a["id"] != b["id"]

    def test_unknown_backlog_item(self, client):
        response = client.post("/api/purchase-orders", json=po_payload("does-not-exist"))
        assert response.status_code == 404

    def test_second_po_for_same_item_rejected(self, client, backlog_item_id):
        assert client.post("/api/purchase-orders", json=po_payload(backlog_item_id)).status_code == 201
        response = client.post("/api/purchase-orders", json=po_payload(backlog_item_id))
        assert response.status_code == 409

    @pytest.mark.parametrize(
        "overrides",
        [
            {"supplier_name": "   "},
            {"quantity": 0},
            {"quantity": -5},
            {"unit_cost": -1},
            {"expected_delivery_date": "next tuesday"},
        ],
    )
    def test_invalid_input_rejected(self, client, backlog_item_id, overrides):
        response = client.post("/api/purchase-orders", json=po_payload(backlog_item_id, **overrides))
        assert response.status_code == 400

    def test_missing_required_field_rejected(self, client, backlog_item_id):
        payload = po_payload(backlog_item_id)
        del payload["supplier_name"]
        response = client.post("/api/purchase-orders", json=payload)
        assert response.status_code == 422


class TestGetPurchaseOrder:
    """Test suite for GET /api/purchase-orders/{backlog_item_id}."""

    def test_get_purchase_order(self, client, backlog_item_id):
        created = client.post("/api/purchase-orders", json=po_payload(backlog_item_id)).json()
        response = client.get(f"/api/purchase-orders/{backlog_item_id}")
        assert response.status_code == 200
        assert response.json() == created

    def test_get_purchase_order_not_found(self, client, backlog_item_id):
        response = client.get(f"/api/purchase-orders/{backlog_item_id}")
        assert response.status_code == 404


class TestBacklogPurchaseOrderFlag:
    """The Dashboard relies on /api/backlog to say which items already have a PO."""

    def test_backlog_reports_purchase_order(self, client, backlog_item_id):
        before = {i["id"]: i for i in client.get("/api/backlog").json()}
        assert before[backlog_item_id]["has_purchase_order"] is False
        assert before[backlog_item_id]["purchase_order_id"] is None

        po = client.post("/api/purchase-orders", json=po_payload(backlog_item_id)).json()

        after = {i["id"]: i for i in client.get("/api/backlog").json()}
        assert after[backlog_item_id]["has_purchase_order"] is True
        assert after[backlog_item_id]["purchase_order_id"] == po["id"]
