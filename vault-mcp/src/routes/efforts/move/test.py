"""Tests for POST /efforts/{name}/move."""

import pytest

from routes.efforts._testing import make_client, make_effort_folder, make_vault
from routes.efforts.move.route import router

_WRITEBACK_DISABLED = "write-back disabled; folder relocation depends on it"


@pytest.mark.skip(reason=_WRITEBACK_DISABLED)
def test_move_active_to_backlog(tmp_path):
    pass


@pytest.mark.skip(reason=_WRITEBACK_DISABLED)
def test_move_backlog_to_active(tmp_path):
    pass


@pytest.mark.skip(reason=_WRITEBACK_DISABLED)
def test_move_archive_drops_from_index(tmp_path):
    pass


def test_move_same_state_is_noop(tmp_path):
    vault = make_vault(tmp_path)
    make_effort_folder(vault, "efforts", "alpha", body="# Alpha\n")
    client, _ = make_client(vault, router)

    resp = client.post("/efforts/alpha/move", json={"target": "active"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["archived"] is False
    assert body["effort"]["status"] == "ACTIVE"
    assert (vault / "efforts" / "alpha" / "CLAUDE.md").exists()


def test_move_404_when_missing(tmp_path):
    vault = make_vault(tmp_path)
    client, _ = make_client(vault, router)
    resp = client.post("/efforts/ghost/move", json={"target": "backlog"})
    assert resp.status_code == 404


def test_move_invalid_target_rejected(tmp_path):
    vault = make_vault(tmp_path)
    make_effort_folder(vault, "efforts", "alpha", body="# Alpha\n")
    client, _ = make_client(vault, router)
    resp = client.post("/efforts/alpha/move", json={"target": "deleted"})
    assert resp.status_code == 422
