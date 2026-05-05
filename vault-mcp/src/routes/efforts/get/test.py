"""Tests for GET /efforts/{name}."""

from datetime import date

from routes.efforts._testing import make_client, make_effort_folder, make_vault
from routes.efforts.get.route import router
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


def test_get_effort_success(tmp_path):
    vault = make_vault(tmp_path)
    make_effort_folder(vault, "efforts", "alpha", body="# Alpha\n\nThe goal.\n")
    client, _ = make_client(vault, router)

    resp = client.get("/efforts/alpha")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "alpha"
    assert body["description"] == "The goal."
    assert body["status"] == "ACTIVE"
    assert body["display"]["task_stats"]["num_by_status"] == {
        "OPEN": 0, "CLOSED": 0, "IN_PROGRESS": 0, "BLOCKED": 0,
    }


def test_get_effort_404(tmp_path):
    vault = make_vault(tmp_path)
    client, _ = make_client(vault, router)
    resp = client.get("/efforts/missing")
    assert resp.status_code == 404


def test_get_effort_populates_task_stats(tmp_path):
    vault = make_vault(tmp_path)
    make_effort_folder(vault, "efforts", "alpha", body="# Alpha\n")
    client, app = make_client(vault, router)

    _seed_task(app.db, "alpha", TaskStatus.OPEN)
    _seed_task(app.db, "alpha", TaskStatus.CLOSED)
    _seed_task(app.db, "other", TaskStatus.OPEN)

    resp = client.get("/efforts/alpha")
    assert resp.status_code == 200
    counts = resp.json()["display"]["task_stats"]["num_by_status"]
    assert counts["OPEN"] == 1
    assert counts["CLOSED"] == 1
    assert counts["IN_PROGRESS"] == 0
    assert counts["BLOCKED"] == 0
