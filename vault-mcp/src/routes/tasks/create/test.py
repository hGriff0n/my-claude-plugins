"""Tests for POST /tasks."""

from routes.tasks._testing import make_client, make_effort_folder, make_vault
from routes.tasks.create.route import router
from vault.tasks.parser import ROOT_TASKFILE


def test_create_task_in_root(tmp_path):
    vault = make_vault(tmp_path)
    client, _ = make_client(vault, router)

    resp = client.post("/tasks", json={"text": "Hello world"})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["text"] == "Hello world"
    assert body["effort"] == "none"
    assert body["status"] == "OPEN"
    assert body["type"] == "TASK"
    assert body["id"]


def test_create_task_in_effort(tmp_path):
    vault = make_vault(tmp_path)
    make_effort_folder(vault, "alpha")
    client, _ = make_client(vault, router)

    resp = client.post("/tasks", json={"text": "Effort task", "effort": "alpha"})
    assert resp.status_code == 201, resp.text
    assert resp.json()["effort"] == "alpha"


def test_create_400_unknown_effort(tmp_path):
    vault = make_vault(tmp_path)
    client, _ = make_client(vault, router)

    resp = client.post("/tasks", json={"text": "x", "effort": "ghost"})
    assert resp.status_code == 400


def test_create_with_parent(tmp_path):
    vault = make_vault(tmp_path)
    (vault / ROOT_TASKFILE).write_text(
        "- [ ] Parent 🆔 par001\n", encoding="utf-8"
    )
    client, _ = make_client(vault, router)

    resp = client.post("/tasks", json={"text": "Child", "parent": "par001"})
    assert resp.status_code == 201, resp.text
    assert resp.json()["dependencies"]["parent"] == "par001"


def test_create_400_unknown_parent(tmp_path):
    vault = make_vault(tmp_path)
    client, _ = make_client(vault, router)

    resp = client.post("/tasks", json={"text": "x", "parent": "ghost1"})
    assert resp.status_code == 400


def test_create_milestone(tmp_path):
    vault = make_vault(tmp_path)
    client, _ = make_client(vault, router)

    resp = client.post("/tasks", json={"text": "Phase one", "type": "MILESTONE"})
    assert resp.status_code == 201, resp.text
    assert resp.json()["type"] == "MILESTONE"
