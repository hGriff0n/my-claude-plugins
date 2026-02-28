"""
Tests for the REST API routes.

Uses FastAPI TestClient against real VaultCache with a temp vault.
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from api.routes import register_routes


def create_app(cache) -> FastAPI:
    app = FastAPI()
    router = APIRouter(prefix="/api")
    register_routes(router, cache)
    app.include_router(router)
    return app
from cache.vault_cache import VaultCache


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir()

    (vault / "TASKS.md").write_text(
        "### Open\n\n"
        "- [ ] Buy groceries 🆔 tsk001 ➕ 2026-01-01 📅 2026-02-28 #stub\n"
        "- [ ] Call dentist 🆔 tsk002 ➕ 2026-01-02 ⛔ tsk001\n\n"
        "### Done\n\n"
        "- [x] File taxes 🆔 tsk003 ➕ 2025-12-01 ✅ 2026-01-15\n",
        encoding="utf-8",
    )

    active = vault / "efforts" / "side-project"
    active.mkdir(parents=True)
    (active / "CLAUDE.md").write_text("# side-project\n")
    (active / "TASKS.md").write_text(
        "### Open\n\n"
        "- [ ] Set up repo 🆔 sp001 ➕ 2026-01-10\n",
        encoding="utf-8",
    )

    backlog = vault / "efforts" / "__backlog" / "archived"
    backlog.mkdir(parents=True)
    (backlog / "CLAUDE.md").write_text("# archived\n")

    return vault


@pytest.fixture
def client(tmp_path):
    vault = _make_vault(tmp_path)
    cache = VaultCache()
    cache.initialize(vault, set())
    app = create_app(cache)
    return TestClient(app)


@pytest.fixture
def vault_path(tmp_path):
    return _make_vault(tmp_path)


@pytest.fixture
def client_with_vault(tmp_path):
    vault = _make_vault(tmp_path)
    cache = VaultCache()
    cache.initialize(vault, set())
    app = create_app(cache)
    return TestClient(app), vault


# ---------------------------------------------------------------------------
# Task endpoints
# ---------------------------------------------------------------------------

class TestTaskEndpoints:
    def test_list_tasks(self, client):
        resp = client.get("/api/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 2  # tsk001, tsk002 are open

    def test_list_tasks_filter_status(self, client):
        resp = client.get("/api/tasks", params={"status": "done"})
        assert resp.status_code == 200
        ids = {t["id"] for t in resp.json()}
        assert "tsk003" in ids

    def test_list_tasks_filter_effort(self, client):
        resp = client.get("/api/tasks", params={"status": "open,in-progress,done", "effort": "side-project"})
        assert resp.status_code == 200
        ids = {t["id"] for t in resp.json()}
        assert "sp001" in ids
        assert "tsk001" not in ids

    def test_list_tasks_filter_blocked(self, client):
        resp = client.get("/api/tasks", params={"status": "open,in-progress,done", "blocked": True})
        assert resp.status_code == 200
        ids = {t["id"] for t in resp.json()}
        assert "tsk002" in ids

    def test_get_task(self, client):
        resp = client.get("/api/tasks/tsk001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Buy groceries"

    def test_get_task_not_found(self, client):
        resp = client.get("/api/tasks/nonexistent")
        assert resp.status_code == 404

    def test_add_task(self, client_with_vault):
        client, vault = client_with_vault
        resp = client.post("/api/tasks", json={
            "title": "New REST task",
            "file_path": str(vault / "TASKS.md"),
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "New REST task"
        assert "id" in data

    def test_update_task(self, client):
        resp = client.patch("/api/tasks/tsk001", json={"status": "done"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "done"

    def test_update_task_not_found(self, client):
        resp = client.patch("/api/tasks/nonexistent", json={"status": "done"})
        assert resp.status_code == 404

    def test_get_blockers(self, client):
        resp = client.get("/api/tasks/tsk002/blockers")
        assert resp.status_code == 200
        data = resp.json()
        blocker_ids = {b["id"] for b in data["blocked_by"]}
        assert "tsk001" in blocker_ids

    def test_cache_status(self, client):
        resp = client.get("/api/cache/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "tasks_indexed" in data


# ---------------------------------------------------------------------------
# Effort endpoints
# ---------------------------------------------------------------------------

class TestEffortEndpoints:
    def test_list_efforts(self, client):
        resp = client.get("/api/efforts")
        assert resp.status_code == 200
        names = {e["name"] for e in resp.json()}
        assert "side-project" in names

    def test_list_efforts_filter_active(self, client):
        resp = client.get("/api/efforts", params={"status": "active"})
        assert resp.status_code == 200
        names = {e["name"] for e in resp.json()}
        assert "side-project" in names
        assert "archived" not in names

    def test_get_effort(self, client):
        resp = client.get("/api/efforts/side-project")
        assert resp.status_code == 200
        assert resp.json()["name"] == "side-project"

    def test_get_effort_not_found(self, client):
        resp = client.get("/api/efforts/nonexistent")
        assert resp.status_code == 404

    def test_focus_workflow(self, client):
        # Initially no focus
        resp = client.get("/api/efforts/focus")
        assert resp.status_code == 200
        assert resp.json()["focused"] is None

        # Set focus
        resp = client.put("/api/efforts/focus", json={"name": "side-project"})
        assert resp.status_code == 200
        assert resp.json()["focused"] == "side-project"

        # Verify focus
        resp = client.get("/api/efforts/focus")
        assert resp.status_code == 200
        assert resp.json()["name"] == "side-project"

        # Clear focus
        resp = client.delete("/api/efforts/focus")
        assert resp.status_code == 200
        assert resp.json()["focused"] is None

    def test_scan_efforts(self, client):
        resp = client.post("/api/efforts/scan")
        assert resp.status_code == 200
        data = resp.json()
        assert data["scanned"] is True
        assert "side-project" in data["active"]


class TestEffortCreateEndpoints:
    def test_create_effort(self, client_with_vault):
        client, vault = client_with_vault
        efforts_dir = vault / "efforts"

        def fake_obsidian(*args):
            if "create" in args and any("CLAUDE.md" in a for a in args):
                new_dir = efforts_dir / "new-effort"
                new_dir.mkdir(parents=True, exist_ok=True)
                (new_dir / "CLAUDE.md").write_text("# new-effort\n", encoding="utf-8")
            return Mock(returncode=0, stderr="")

        with patch("api.effort_handlers._obsidian", side_effect=fake_obsidian):
            resp = client.post("/api/efforts", json={"name": "new-effort"})
        assert resp.status_code == 201
        assert resp.json()["name"] == "new-effort"

    def test_create_duplicate_effort(self, client):
        resp = client.post("/api/efforts", json={"name": "side-project"})
        assert resp.status_code == 400

    def test_create_obsidian_failure(self, client):
        with patch("api.effort_handlers._obsidian", return_value=Mock(returncode=1, stderr="template not found")):
            resp = client.post("/api/efforts", json={"name": "fail-effort"})
        assert resp.status_code == 400


class TestEffortMoveEndpoints:
    def test_move_to_backlog(self, client_with_vault):
        client, vault = client_with_vault
        efforts_dir = vault / "efforts"

        def fake_obsidian(*args):
            if "move" in args:
                backlog_dir = efforts_dir / "__backlog" / "side-project"
                backlog_dir.mkdir(parents=True, exist_ok=True)
                (backlog_dir / "CLAUDE.md").write_text("# side-project\n", encoding="utf-8")
                claude_active = efforts_dir / "side-project" / "CLAUDE.md"
                if claude_active.exists():
                    claude_active.unlink()
            return Mock(returncode=0, stderr="")

        with patch("api.effort_handlers._obsidian", side_effect=fake_obsidian):
            resp = client.post("/api/efforts/side-project/move", json={"backlog": True})
        assert resp.status_code == 200

    def test_move_not_found(self, client):
        resp = client.post("/api/efforts/nonexistent/move", json={"backlog": True})
        assert resp.status_code == 404

    def test_move_invalid_transition(self, client):
        """Active effort cannot be activated again."""
        resp = client.post("/api/efforts/side-project/move", json={"backlog": False, "archive": False})
        assert resp.status_code == 400

    def test_move_partial_failure(self, client):
        with patch("api.effort_handlers._obsidian", return_value=Mock(returncode=1, stderr="failed")):
            resp = client.post("/api/efforts/side-project/move", json={"backlog": True})
        assert resp.status_code == 400
