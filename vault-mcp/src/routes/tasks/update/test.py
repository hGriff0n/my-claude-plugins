"""Tests for PATCH /tasks/{id}."""

from routes.tasks._testing import make_client, make_vault
from routes.tasks.update.route import router
from vault.tasks.parser import ROOT_TASKFILE


def test_update_text(tmp_path):
    vault = make_vault(tmp_path)
    (vault / ROOT_TASKFILE).write_text(
        "- [ ] Old 🆔 ut0001\n", encoding="utf-8"
    )
    client, _ = make_client(vault, router)

    resp = client.patch("/tasks/ut0001", json={"text": "New title"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["text"] == "New title"


def test_update_status(tmp_path):
    vault = make_vault(tmp_path)
    (vault / ROOT_TASKFILE).write_text(
        "- [ ] T 🆔 us0001\n", encoding="utf-8"
    )
    client, _ = make_client(vault, router)

    resp = client.patch("/tasks/us0001", json={"status": "CLOSED"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "CLOSED"


def test_update_tags(tmp_path):
    vault = make_vault(tmp_path)
    (vault / ROOT_TASKFILE).write_text(
        "- [ ] T 🆔 ug0001 #old\n", encoding="utf-8"
    )
    client, _ = make_client(vault, router)

    resp = client.patch("/tasks/ug0001", json={"tags": ["new"]})
    assert resp.status_code == 200
    assert resp.json()["tags"] == ["new"]


def test_update_dependencies(tmp_path):
    vault = make_vault(tmp_path)
    (vault / ROOT_TASKFILE).write_text(
        "- [ ] A 🆔 ud0001\n- [ ] B 🆔 ud0002\n",
        encoding="utf-8",
    )
    client, _ = make_client(vault, router)

    resp = client.patch(
        "/tasks/ud0001",
        json={
            "dependencies": {
                "blocked": ["ud0002"], "parent": "", "children": []
            }
        },
    )
    assert resp.status_code == 200
    assert resp.json()["dependencies"]["blocked"] == ["ud0002"]


def test_update_400_unknown_dependency(tmp_path):
    vault = make_vault(tmp_path)
    (vault / ROOT_TASKFILE).write_text(
        "- [ ] T 🆔 ux0001\n", encoding="utf-8"
    )
    client, _ = make_client(vault, router)

    resp = client.patch(
        "/tasks/ux0001",
        json={
            "dependencies": {
                "blocked": ["ghost1"], "parent": "", "children": []
            }
        },
    )
    assert resp.status_code == 400


def test_update_404_when_missing(tmp_path):
    vault = make_vault(tmp_path)
    client, _ = make_client(vault, router)

    resp = client.patch("/tasks/ghost1", json={"text": "x"})
    assert resp.status_code == 404
