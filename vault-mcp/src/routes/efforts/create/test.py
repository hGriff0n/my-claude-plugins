"""Tests for POST /efforts."""

from unittest.mock import patch

from routes.efforts._testing import (
    fake_obsidian_create,
    make_client,
    make_effort_folder,
    make_vault,
)
from routes.efforts.create.route import router


def test_create_effort_success(tmp_path):
    vault = make_vault(tmp_path)
    client, _ = make_client(vault, router)

    with patch("vault.efforts.parser.obsidian_cli", side_effect=fake_obsidian_create(vault)):
        resp = client.post("/efforts", json={"name": "alpha"})

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "alpha"
    assert body["status"] == "ACTIVE"
    assert body["display"]["task_stats"]["num_by_status"] == {
        "OPEN": 0, "CLOSED": 0, "IN_PROGRESS": 0, "BLOCKED": 0,
    }
    for f in ("00 README.md", "CLAUDE.md", "01 TASKS.md"):
        assert (vault / "efforts" / "alpha" / f).exists()


def test_create_rejects_duplicate_active(tmp_path):
    vault = make_vault(tmp_path)
    make_effort_folder(vault, "efforts", "alpha", body="# Alpha\n")
    client, _ = make_client(vault, router)

    resp = client.post("/efforts", json={"name": "alpha"})
    assert resp.status_code == 400


def test_create_rejects_duplicate_backlog(tmp_path):
    vault = make_vault(tmp_path)
    make_effort_folder(vault, "efforts", "__backlog", "alpha", body="# Alpha\n")
    client, _ = make_client(vault, router)

    resp = client.post("/efforts", json={"name": "alpha"})
    assert resp.status_code == 400


def test_create_returns_400_on_scaffold_failure(tmp_path):
    from unittest.mock import Mock

    vault = make_vault(tmp_path)
    client, _ = make_client(vault, router)

    failing = Mock(returncode=1, stdout="", stderr="template not found")
    with patch("vault.efforts.parser.obsidian_cli", return_value=failing):
        resp = client.post("/efforts", json={"name": "alpha"})

    assert resp.status_code == 400
