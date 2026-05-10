"""Tests for GET /tasks."""

from routes.tasks._testing import make_client, make_effort_folder, make_vault
from routes.tasks.list.route import router
from vault.tasks.parser import ROOT_TASKFILE


def _seed(vault, root_content="", effort_content=None):
    (vault / ROOT_TASKFILE).write_text(root_content, encoding="utf-8")
    if effort_content is not None:
        eff = make_effort_folder(vault, "alpha")
        (eff / ROOT_TASKFILE).write_text(effort_content, encoding="utf-8")


def test_list_all(tmp_path):
    vault = make_vault(tmp_path)
    _seed(
        vault,
        root_content=(
            "- [ ] Alpha 🆔 ta0001\n"
            "- [x] Beta 🆔 ta0002\n"
        ),
    )
    client, _ = make_client(vault, router)

    resp = client.get("/tasks")
    assert resp.status_code == 200
    ids = {t["id"] for t in resp.json()["tasks"]}
    assert ids == {"ta0001", "ta0002"}


def test_filter_by_status(tmp_path):
    vault = make_vault(tmp_path)
    _seed(
        vault,
        root_content=(
            "- [ ] Alpha 🆔 ts0001\n"
            "- [x] Beta 🆔 ts0002\n"
        ),
    )
    client, _ = make_client(vault, router)

    resp = client.get("/tasks?status=CLOSED")
    assert resp.status_code == 200
    tasks = resp.json()["tasks"]
    assert len(tasks) == 1
    assert tasks[0]["id"] == "ts0002"


def test_filter_by_effort(tmp_path):
    vault = make_vault(tmp_path)
    _seed(
        vault,
        root_content="- [ ] Root 🆔 te0001\n",
        effort_content="- [ ] In alpha 🆔 te0002\n",
    )
    client, _ = make_client(vault, router)

    resp = client.get("/tasks?effort=alpha")
    assert resp.status_code == 200
    tasks = resp.json()["tasks"]
    assert len(tasks) == 1
    assert tasks[0]["id"] == "te0002"


def test_filter_by_tag(tmp_path):
    vault = make_vault(tmp_path)
    _seed(
        vault,
        root_content=(
            "- [ ] Tagged 🆔 tg0001 #stub\n"
            "- [ ] Plain 🆔 tg0002\n"
        ),
    )
    client, _ = make_client(vault, router)

    resp = client.get("/tasks?tag=stub")
    assert resp.status_code == 200
    tasks = resp.json()["tasks"]
    assert len(tasks) == 1
    assert tasks[0]["id"] == "tg0001"


def test_filter_by_type(tmp_path):
    vault = make_vault(tmp_path)
    _seed(
        vault,
        root_content=(
            "#### Phase one 🆔 mil001\n"
            "- [ ] Sub 🆔 sub001\n"
        ),
    )
    client, _ = make_client(vault, router)

    resp = client.get("/tasks?type=MILESTONE")
    assert resp.status_code == 200
    tasks = resp.json()["tasks"]
    assert len(tasks) == 1
    assert tasks[0]["id"] == "mil001"


def test_due_or_scheduled_before_is_or(tmp_path):
    vault = make_vault(tmp_path)
    _seed(
        vault,
        root_content=(
            "- [ ] Due only 🆔 td0001 📅 2026-01-10\n"
            "- [ ] Scheduled only 🆔 td0002 ⏳ 2026-01-10\n"
            "- [ ] Neither 🆔 td0003\n"
        ),
    )
    client, _ = make_client(vault, router)

    resp = client.get("/tasks?due_before=2026-01-15&scheduled_before=2026-01-15")
    assert resp.status_code == 200
    ids = {t["id"] for t in resp.json()["tasks"]}
    assert ids == {"td0001", "td0002"}


def test_empty_list(tmp_path):
    vault = make_vault(tmp_path)
    client, _ = make_client(vault, router)
    resp = client.get("/tasks")
    assert resp.status_code == 200
    assert resp.json() == {"tasks": [], "next_page_token": None}
