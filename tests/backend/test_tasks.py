"""
Tests for task API endpoints.
"""
import pytest

import main


@pytest.fixture(autouse=True)
def clean_tasks():
    """Tasks live in module-level memory, so reset them around every test."""
    main.tasks.clear()
    yield
    main.tasks.clear()


NEW_TASK = {"title": "Reorder PCB stock", "priority": "high", "dueDate": "2025-10-20"}


class TestTasksEndpoints:
    """Test suite for task-related endpoints."""

    def test_get_tasks_empty(self, client):
        """No tasks exist until one is created."""
        response = client.get("/api/tasks")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_task(self, client):
        """Creating a task returns 201 with a pending task and a new id."""
        response = client.post("/api/tasks", json=NEW_TASK)
        assert response.status_code == 201

        task = response.json()
        assert task["title"] == "Reorder PCB stock"
        assert task["priority"] == "high"
        assert task["dueDate"] == "2025-10-20"
        assert task["status"] == "pending"
        # Must stay above the frontend's built-in task ids (1-4)
        assert task["id"] > 1000

    def test_create_task_trims_title(self, client):
        response = client.post("/api/tasks", json={**NEW_TASK, "title": "  Padded  "})
        assert response.status_code == 201
        assert response.json()["title"] == "Padded"

    def test_create_task_defaults_priority(self, client):
        response = client.post(
            "/api/tasks", json={"title": "No priority", "dueDate": "2025-10-20"}
        )
        assert response.status_code == 201
        assert response.json()["priority"] == "medium"

    def test_create_task_blank_title_rejected(self, client):
        response = client.post("/api/tasks", json={**NEW_TASK, "title": "   "})
        assert response.status_code == 400

    def test_create_task_invalid_priority_rejected(self, client):
        response = client.post("/api/tasks", json={**NEW_TASK, "priority": "urgent"})
        assert response.status_code == 422

    def test_create_task_missing_due_date_rejected(self, client):
        response = client.post("/api/tasks", json={"title": "No date"})
        assert response.status_code == 422

    def test_tasks_listed_newest_first_with_unique_ids(self, client):
        first = client.post("/api/tasks", json={**NEW_TASK, "title": "first"}).json()
        second = client.post("/api/tasks", json={**NEW_TASK, "title": "second"}).json()
        assert first["id"] != second["id"]

        listed = client.get("/api/tasks").json()
        assert [t["title"] for t in listed] == ["second", "first"]

    def test_toggle_task(self, client):
        """Toggling flips pending <-> completed."""
        task_id = client.post("/api/tasks", json=NEW_TASK).json()["id"]

        response = client.patch(f"/api/tasks/{task_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "completed"

        response = client.patch(f"/api/tasks/{task_id}")
        assert response.json()["status"] == "pending"

    def test_toggle_task_not_found(self, client):
        response = client.patch("/api/tasks/99999")
        assert response.status_code == 404

    def test_delete_task(self, client):
        task_id = client.post("/api/tasks", json=NEW_TASK).json()["id"]

        response = client.delete(f"/api/tasks/{task_id}")
        assert response.status_code == 200
        assert client.get("/api/tasks").json() == []

    def test_delete_task_not_found(self, client):
        response = client.delete("/api/tasks/99999")
        assert response.status_code == 404
