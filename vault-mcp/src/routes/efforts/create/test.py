"""Tests for POST /efforts."""

import pytest

from routes.efforts._testing import (
    make_client,
    make_effort_folder,
    make_vault,
)
from routes.efforts.create.route import router

_WRITEBACK_DISABLED = "write-back disabled; re-enable when scaffold path returns"


@pytest.mark.skip(reason=_WRITEBACK_DISABLED)
def test_create_effort_success(tmp_path):
    pass


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


@pytest.mark.skip(reason=_WRITEBACK_DISABLED)
def test_create_returns_400_on_scaffold_failure(tmp_path):
    pass
