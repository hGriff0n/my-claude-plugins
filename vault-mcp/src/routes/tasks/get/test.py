"""Tests for GET /tasks/{id}."""

from routes.tasks._testing import make_client, make_vault
from routes.tasks.get.route import router
from vault.tasks.parser import ROOT_TASKFILE


def test_get_task(tmp_path):
    vault = make_vault(tmp_path)
    (vault / ROOT_TASKFILE).write_text(
        "- [ ] My task 🆔 abc123\n", encoding="utf-8"
    )
    client, _ = make_client(vault, router)

    resp = client.get("/tasks/abc123")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == "abc123"
    assert body["text"] == "My task"


def test_get_404_when_missing(tmp_path):
    vault = make_vault(tmp_path)
    client, _ = make_client(vault, router)

    resp = client.get("/tasks/ghost1")
    assert resp.status_code == 404
