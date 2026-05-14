"""Tests for POST /tasks/archive."""

from unittest.mock import Mock, patch

from routes.tasks._testing import make_client, make_vault
from routes.tasks.archive.route import router
from routes.efforts._testing import fake_obsidian_create
from vault.tasks.parser import ROOT_TASKFILE


def _post_archive(client, body=None):
    return client.post("/tasks/archive", json=body or {})


def test_archive_default_archives_all_closed(tmp_path):
    vault = make_vault(tmp_path)
    (vault / ROOT_TASKFILE).write_text(
        "- [x] Done one ✅ 2026-05-01 🆔 ar0001\n"
        "- [x] Done two ✅ 2026-05-02 🆔 ar0002\n"
        "- [ ] Open ✅ 2026-05-01 🆔 ar0003\n",
        encoding="utf-8",
    )
    client, app = make_client(vault, router)

    with patch(
        "routes.tasks.archive.route.obsidian_cli",
        side_effect=fake_obsidian_create(vault),
    ):
        resp = _post_archive(client)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["dry_run"] is False
    assert sum(data["archived"].values()) == 2
    assert data["failures"] == []
    closed_ids = {u["id"] for u in data["updates"] if u["action"] == "CLOSED"}
    assert closed_ids == {"ar0001", "ar0002"}

    remaining = {t.id for t in app.db.query('SELECT * FROM "task"')}
    assert "ar0001" not in remaining
    assert "ar0002" not in remaining
    assert "ar0003" in remaining


def test_archive_explicit_ids(tmp_path):
    vault = make_vault(tmp_path)
    (vault / ROOT_TASKFILE).write_text(
        "- [x] One ✅ 2026-05-01 🆔 ar1001\n"
        "- [x] Two ✅ 2026-05-01 🆔 ar1002\n",
        encoding="utf-8",
    )
    client, app = make_client(vault, router)

    with patch(
        "routes.tasks.archive.route.obsidian_cli",
        side_effect=fake_obsidian_create(vault),
    ):
        resp = _post_archive(client, {"ids": ["ar1001"]})

    assert resp.status_code == 200, resp.text
    closed = {u["id"] for u in resp.json()["updates"] if u["action"] == "CLOSED"}
    assert closed == {"ar1001"}
    remaining = {t.id for t in app.db.query('SELECT * FROM "task"')}
    assert remaining == {"ar1002"}


def test_archive_400_when_id_unknown(tmp_path):
    vault = make_vault(tmp_path)
    client, _ = make_client(vault, router)
    resp = _post_archive(client, {"ids": ["ghost1"]})
    assert resp.status_code == 400


def test_archive_400_when_id_not_closed(tmp_path):
    vault = make_vault(tmp_path)
    (vault / ROOT_TASKFILE).write_text(
        "- [ ] Open 🆔 ar2001\n", encoding="utf-8"
    )
    client, _ = make_client(vault, router)
    resp = _post_archive(client, {"ids": ["ar2001"]})
    assert resp.status_code == 400


def test_archive_dry_run(tmp_path):
    vault = make_vault(tmp_path)
    (vault / ROOT_TASKFILE).write_text(
        "- [x] Done ✅ 2026-05-01 🆔 ar3001\n", encoding="utf-8"
    )
    client, app = make_client(vault, router)

    with patch("routes.tasks.archive.route.obsidian_cli") as cli:
        resp = _post_archive(client, {"dry_run": True})

    assert resp.status_code == 200
    data = resp.json()
    assert data["dry_run"] is True
    assert sum(data["archived"].values()) == 1
    cli.assert_not_called()
    remaining = {t.id for t in app.db.query('SELECT * FROM "task"')}
    assert "ar3001" in remaining


def test_archive_reopens_parent_with_open_descendant(tmp_path):
    vault = make_vault(tmp_path)
    (vault / ROOT_TASKFILE).write_text(
        "- [x] Parent ✅ 2026-05-01 🆔 ar4001\n"
        "    - [ ] Open child 🆔 ar4002\n",
        encoding="utf-8",
    )
    client, app = make_client(vault, router)

    with patch(
        "routes.tasks.archive.route.obsidian_cli",
        side_effect=fake_obsidian_create(vault),
    ):
        resp = _post_archive(client)

    assert resp.status_code == 200
    data = resp.json()
    opened = {u["id"] for u in data["updates"] if u["action"] == "OPENED"}
    closed = {u["id"] for u in data["updates"] if u["action"] == "CLOSED"}
    assert "ar4001" in opened
    assert "ar4001" not in closed

    parent = next(
        t for t in app.db.query('SELECT * FROM "task"') if t.id == "ar4001"
    )
    assert parent.status.value in {"OPEN", "BLOCKED"}
    assert "ar4002" in parent.dependencies.blocked


def test_archive_creates_daily_note_without_content_arg(tmp_path):
    vault = make_vault(tmp_path)
    (vault / ROOT_TASKFILE).write_text(
        "- [x] Done ✅ 2026-05-01 🆔 ar6001\n", encoding="utf-8",
    )
    client, _ = make_client(vault, router)

    with patch(
        "routes.tasks.archive.route.obsidian_cli",
        side_effect=fake_obsidian_create(vault),
    ) as cli:
        resp = _post_archive(client)

    assert resp.status_code == 200
    create_calls = [c.args for c in cli.call_args_list if c.args[0] == "create"]
    assert len(create_calls) == 1
    assert "template=daily" in create_calls[0]
    assert not any(a.startswith("content=") for a in create_calls[0])


def test_archive_appends_heading_and_sets_property(tmp_path):
    vault = make_vault(tmp_path)
    (vault / ROOT_TASKFILE).write_text(
        "- [x] One ✅ 2026-05-01 🆔 ar7001\n"
        "- [x] Two ✅ 2026-05-01 🆔 ar7002\n",
        encoding="utf-8",
    )
    client, _ = make_client(vault, router)

    with patch(
        "routes.tasks.archive.route.obsidian_cli",
        side_effect=fake_obsidian_create(vault),
    ) as cli:
        resp = _post_archive(client)

    assert resp.status_code == 200
    cmds = [c.args for c in cli.call_args_list]

    heading_appends = [
        c for c in cmds
        if c[0] == "append" and "content=### Completed Tasks" in c[1:]
    ]
    assert len(heading_appends) == 1

    prop_sets = [c for c in cmds if c[0] == "property:set"]
    assert len(prop_sets) == 1
    args = prop_sets[0]
    assert "name=completed_tasks" in args
    assert "value=2" in args
    assert "type=number" in args


def test_archive_skips_heading_when_section_exists(tmp_path):
    vault = make_vault(tmp_path)
    (vault / ROOT_TASKFILE).write_text(
        "- [x] Done ✅ 2026-05-01 🆔 ar8001\n", encoding="utf-8",
    )
    daily = vault / "areas" / "journal" / "2026" / "05 May" / "01.md"
    daily.parent.mkdir(parents=True, exist_ok=True)
    daily.write_text("### Completed Tasks\n\n- existing\n", encoding="utf-8")
    client, _ = make_client(vault, router)

    with patch(
        "routes.tasks.archive.route.obsidian_cli",
        side_effect=fake_obsidian_create(vault),
    ) as cli:
        resp = _post_archive(client)

    assert resp.status_code == 200
    cmds = [c.args for c in cli.call_args_list]
    assert not any(c[0] == "create" for c in cmds)
    assert not any(
        c[0] == "append" and "content=### Completed Tasks" in c[1:]
        for c in cmds
    )


def test_archive_increments_existing_completed_tasks_property(tmp_path):
    vault = make_vault(tmp_path)
    (vault / ROOT_TASKFILE).write_text(
        "- [x] Done ✅ 2026-05-01 🆔 ar9001\n", encoding="utf-8",
    )
    client, _ = make_client(vault, router)

    base_fake = fake_obsidian_create(vault)

    def fake(*args: str):
        if args and args[0] == "property:read":
            return Mock(returncode=0, stdout="5", stderr="")
        return base_fake(*args)

    with patch("routes.tasks.archive.route.obsidian_cli", side_effect=fake) as cli:
        resp = _post_archive(client)

    assert resp.status_code == 200
    prop_sets = [c.args for c in cli.call_args_list if c.args[0] == "property:set"]
    assert len(prop_sets) == 1
    assert "value=6" in prop_sets[0]


def test_archive_groups_by_completion_date(tmp_path):
    vault = make_vault(tmp_path)
    (vault / ROOT_TASKFILE).write_text(
        "- [x] Day1 ✅ 2026-05-01 🆔 ar5001\n"
        "- [x] Day2 ✅ 2026-05-02 🆔 ar5002\n",
        encoding="utf-8",
    )
    client, _ = make_client(vault, router)

    with patch(
        "routes.tasks.archive.route.obsidian_cli",
        side_effect=fake_obsidian_create(vault),
    ):
        resp = _post_archive(client)

    archived = resp.json()["archived"]
    assert len(archived) == 2
    assert all(count == 1 for count in archived.values())
    assert any("2026/05 May/01.md" in k for k in archived)
    assert any("2026/05 May/02.md" in k for k in archived)
