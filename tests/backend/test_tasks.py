"""
Tests for the /api/tasks endpoints.
"""
import pytest


NEW_TASK = {"title": "Review Q4 stock", "priority": "high", "dueDate": "2025-10-08"}


class TestTasksEndpoints:
    """Test suite for task endpoints."""

    def test_get_tasks_empty(self, client):
        """The list endpoint exists and starts empty (it used to 404)."""
        response = client.get("/api/tasks")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_task(self, client):
        response = client.post("/api/tasks", json=NEW_TASK)
        assert response.status_code == 201

        task = response.json()
        assert task["title"] == NEW_TASK["title"]
        assert task["priority"] == "high"
        assert task["dueDate"] == "2025-10-08"
        assert task["status"] == "pending"
        # Must not collide with the client's hard-coded tasks (ids 1-4)
        assert task["id"] >= 1000

    def test_created_tasks_listed_newest_first(self, client):
        first = client.post("/api/tasks", json=NEW_TASK).json()
        second = client.post("/api/tasks", json={**NEW_TASK, "title": "Second"}).json()
        assert first["id"] != second["id"]

        listed = client.get("/api/tasks").json()
        assert [t["id"] for t in listed] == [second["id"], first["id"]]

    def test_toggle_task(self, client):
        task_id = client.post("/api/tasks", json=NEW_TASK).json()["id"]

        response = client.patch(f"/api/tasks/{task_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "completed"

        response = client.patch(f"/api/tasks/{task_id}")
        assert response.json()["status"] == "pending"

    def test_delete_task(self, client):
        task_id = client.post("/api/tasks", json=NEW_TASK).json()["id"]

        assert client.delete(f"/api/tasks/{task_id}").status_code == 200
        assert client.get("/api/tasks").json() == []

    def test_unknown_task_returns_404(self, client):
        assert client.patch("/api/tasks/9999").status_code == 404
        assert client.delete("/api/tasks/9999").status_code == 404

    @pytest.mark.parametrize("payload", [
        {**NEW_TASK, "title": "   "},
        {**NEW_TASK, "priority": "urgent"},
        {**NEW_TASK, "dueDate": "next week"},
    ])
    def test_create_task_validation(self, client, payload):
        assert client.post("/api/tasks", json=payload).status_code == 400
