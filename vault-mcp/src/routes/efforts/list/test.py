"""Tests for GET /efforts."""

from datetime import date

from routes.efforts._testing import make_client, make_effort_folder, make_vault
from routes.efforts.list.route import router
from schemas.tasks import Dependencies, Task, TaskStatus, TaskType
from schemas.time import TimeBlock


def _seed_task(db, effort: str, status: TaskStatus) -> None:
    db.register(Task, system="tasks")
    null = date.min
    task = Task(
        id=f"t-{effort}-{status.value}",
        type=TaskType.TASK,
        status=status,
        text="x",
        effort=effort,
        notes=[],
        tags=[],
        dependencies=Dependencies(blocked=[], parent="", children=[]),
        time_details=TimeBlock(created=null, last_updated=null, due=null, scheduled=null),
    )
    db.update(task)


def test_list_all(tmp_path):
    vault = make_vault(tmp_path)
    make_effort_folder(vault, "efforts", "alpha", body="# Alpha\n")
    make_effort_folder(vault, "efforts", "__backlog", "beta", body="# Beta\n")
    client, _ = make_client(vault, router)

    resp = client.get("/efforts")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    names = {e["name"] for e in body["efforts"]}
    assert names == {"alpha", "beta"}
    assert body["next_page_token"] is None


def test_list_filter_active(tmp_path):
    vault = make_vault(tmp_path)
    make_effort_folder(vault, "efforts", "alpha", body="# Alpha\n")
    make_effort_folder(vault, "efforts", "__backlog", "beta", body="# Beta\n")
    client, _ = make_client(vault, router)

    resp = client.get("/efforts", params={"status": "ACTIVE"})
    assert resp.status_code == 200
    names = {e["name"] for e in resp.json()["efforts"]}
    assert names == {"alpha"}


def test_list_filter_backlog(tmp_path):
    vault = make_vault(tmp_path)
    make_effort_folder(vault, "efforts", "alpha", body="# Alpha\n")
    make_effort_folder(vault, "efforts", "__backlog", "beta", body="# Beta\n")
    client, _ = make_client(vault, router)

    resp = client.get("/efforts", params={"status": "BACKLOG"})
    assert resp.status_code == 200
    names = {e["name"] for e in resp.json()["efforts"]}
    assert names == {"beta"}


def test_list_zeroed_stats_when_include_task_stats_false(tmp_path):
    vault = make_vault(tmp_path)
    make_effort_folder(vault, "efforts", "alpha", body="# Alpha\n")
    client, app = make_client(vault, router)
    _seed_task(app.db, "alpha", TaskStatus.OPEN)

    resp = client.get("/efforts")
    counts = resp.json()["efforts"][0]["display"]["task_stats"]["num_by_status"]
    assert counts == {"OPEN": 0, "CLOSED": 0, "IN_PROGRESS": 0, "BLOCKED": 0}


def test_list_with_task_stats(tmp_path):
    vault = make_vault(tmp_path)
    make_effort_folder(vault, "efforts", "alpha", body="# Alpha\n")
    make_effort_folder(vault, "efforts", "beta", body="# Beta\n")
    client, app = make_client(vault, router)
    _seed_task(app.db, "alpha", TaskStatus.OPEN)
    _seed_task(app.db, "alpha", TaskStatus.IN_PROGRESS)
    _seed_task(app.db, "beta", TaskStatus.OPEN)

    resp = client.get("/efforts", params={"include_task_stats": True})
    assert resp.status_code == 200
    by_name = {e["name"]: e for e in resp.json()["efforts"]}
    assert by_name["alpha"]["display"]["task_stats"]["num_by_status"]["OPEN"] == 1
    assert by_name["alpha"]["display"]["task_stats"]["num_by_status"]["IN_PROGRESS"] == 1
    assert by_name["beta"]["display"]["task_stats"]["num_by_status"]["OPEN"] == 1
