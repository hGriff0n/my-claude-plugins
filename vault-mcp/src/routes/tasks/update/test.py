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


def test_close_writes_completed_date(tmp_path):
    vault = make_vault(tmp_path)
    path = vault / ROOT_TASKFILE
    path.write_text("- [ ] T 🆔 cd0001\n", encoding="utf-8")
    client, app = make_client(vault, router)

    resp = client.patch("/tasks/cd0001", json={"status": "CLOSED"})
    assert resp.status_code == 200
    assert resp.json()["time_details"]["completed"] is not None

    app.task_parser.flush_file(path)
    assert "✅" in path.read_text(encoding="utf-8")


def test_reopen_clears_completed_date(tmp_path):
    vault = make_vault(tmp_path)
    path = vault / ROOT_TASKFILE
    path.write_text(
        "- [x] T 🆔 cr0001 ✅ 2026-01-01\n", encoding="utf-8"
    )
    client, app = make_client(vault, router)

    resp = client.patch("/tasks/cr0001", json={"status": "OPEN"})
    assert resp.status_code == 200
    assert resp.json()["time_details"]["completed"] is None

    app.task_parser.flush_file(path)
    assert "✅" not in path.read_text(encoding="utf-8")


def test_idless_milestone_not_duplicated_on_flush(tmp_path):
    vault = make_vault(tmp_path)
    path = vault / ROOT_TASKFILE
    path.write_text(
        "#### Release\n\n- [ ] T 🆔 md0001\n", encoding="utf-8"
    )
    client, app = make_client(vault, router)

    resp = client.patch("/tasks/md0001", json={"status": "CLOSED"})
    assert resp.status_code == 200

    app.task_parser.flush_file(path)
    assert path.read_text(encoding="utf-8").count("Release") == 1


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
