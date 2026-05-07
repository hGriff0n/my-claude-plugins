"""Tests for POST /tasks/{id}/archive."""

from routes.tasks._testing import make_client, make_vault
from routes.tasks.archive.route import router
from vault.tasks.parser import ROOT_TASKFILE


def test_archive_closed_task(tmp_path):
    vault = make_vault(tmp_path)
    (vault / ROOT_TASKFILE).write_text(
        "- [x] Done 🆔 ar0001\n- [ ] Keep 🆔 ar0002\n",
        encoding="utf-8",
    )
    client, app = make_client(vault, router)

    resp = client.post("/tasks/ar0001/archive")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"archived": True}
    remaining = {t.id for t in app.db.query('SELECT * FROM "task"')}
    assert "ar0001" not in remaining
    assert "ar0002" in remaining


def test_archive_400_when_not_closed(tmp_path):
    vault = make_vault(tmp_path)
    (vault / ROOT_TASKFILE).write_text(
        "- [ ] Open 🆔 ar0003\n", encoding="utf-8"
    )
    client, _ = make_client(vault, router)

    resp = client.post("/tasks/ar0003/archive")
    assert resp.status_code == 400


def test_archive_404_when_missing(tmp_path):
    vault = make_vault(tmp_path)
    client, _ = make_client(vault, router)

    resp = client.post("/tasks/ghost1/archive")
    assert resp.status_code == 404
