"""
Interactive harness for testing vault-mcp without MCP integration.

Usage:
    python harness.py <VAULT_ROOT> [--exclude .git,.obsidian]

Drops you into an interactive REPL where you can call cache methods directly.
Also runs a quick smoke test on startup to verify parsing/indexing works.
"""

import sys
import os
import json
from pathlib import Path

# Add src/ to path so imports work
sys.path.insert(0, str(Path(__file__).parent / "src"))

from cache.vault_cache import VaultCache
from parsers.effort_scanner import scan_efforts


def smoke_test(cache: VaultCache) -> None:
    """Quick automated checks after initialization."""
    st = cache.status()
    print("\n=== Smoke Test ===")
    print(f"  Vault root:     {st['vault_root']}")
    print(f"  Files indexed:  {st['files_indexed']}")
    print(f"  Tasks indexed:  {st['tasks_indexed']}")
    print(f"  Efforts indexed:{st['efforts_indexed']}")
    print(f"  Exclude dirs:   {st['exclude_dirs']}")

    # Spot-check: query open tasks
    open_tasks = cache.query_tasks(status="open", limit=10)
    print(f"\n  Open tasks (first 10): {len(open_tasks)}")
    for t in open_tasks[:5]:
        indent = "  " * t.indent_level
        print(f"    {indent}[{t.id}] {t.title}")
    if len(open_tasks) > 5:
        print(f"    ... and {len(open_tasks) - 5} more")

    # In-progress
    ip_tasks = cache.query_tasks(status="in-progress", limit=10)
    print(f"\n  In-progress tasks: {len(ip_tasks)}")
    for t in ip_tasks[:5]:
        print(f"    [{t.id}] {t.title}")

    # Done
    done_tasks = cache.query_tasks(status="done", limit=10)
    print(f"\n  Done tasks (first 10): {len(done_tasks)}")
    for t in done_tasks[:5]:
        print(f"    [{t.id}] {t.title}")
    if len(done_tasks) > 5:
        print(f"    ... and {len(done_tasks) - 5} more")

    # Stubs
    stubs = cache.query_tasks(stub=True, limit=10)
    print(f"\n  Stub tasks (first 10): {len(stubs)}")
    for t in stubs[:5]:
        print(f"    [{t.id}] {t.title}")

    # Blocked
    blocked = cache.query_tasks(blocked=True, limit=10)
    print(f"\n  Blocked tasks: {len(blocked)}")
    for t in blocked[:5]:
        print(f"    [{t.id}] {t.title}  blocked_by={t.blocking_ids}")

    # Scheduled (any task with a scheduled date)
    from datetime import date
    today = date.today().isoformat()
    scheduled_today = cache.query_tasks(scheduled_on=today, limit=20)
    print(f"\n  Scheduled for today ({today}): {len(scheduled_today)}")
    for t in scheduled_today:
        indent = "  " * t.indent_level
        print(f"    {indent}[{t.id}] {t.title}  scheduled={t.tags.get('scheduled', '?')}")

    scheduled_upcoming = cache.query_tasks(scheduled_before=today, status="open,in-progress", limit=20)
    print(f"\n  Scheduled on or before today (open/ip): {len(scheduled_upcoming)}")
    for t in scheduled_upcoming:
        indent = "  " * t.indent_level
        print(f"    {indent}[{t.id}] {t.title}  scheduled={t.tags.get('scheduled', '?')}")
    if len(scheduled_upcoming) > 20:
        print(f"    ... and {len(scheduled_upcoming) - 20} more")

    # Efforts
    efforts = cache.list_efforts()
    print(f"\n  Efforts ({len(efforts)}):")
    for e in efforts:
        print(f"    {e.name}  status={e.status.value}  tasks_file={e.tasks_file}")

    print("\n=== Smoke Test Complete ===\n")


def repl(cache: VaultCache) -> None:
    """Simple REPL for interactive exploration."""
    print("Interactive mode. Type 'help' for commands, 'quit' to exit.\n")

    commands = {
        "help":     "Show this help",
        "status":   "Show cache status",
        "tasks":    "List tasks. Usage: tasks [status=open] [effort=name] [scheduled_before=DATE] [scheduled_on=DATE] [due_before=DATE] [parent_id=ID] [include_subtasks=true] [limit=20]",
        "task":     "Get task by ID. Usage: task <id>",
        "efforts":  "List efforts. Usage: efforts [status=active|backlog]",
        "effort":   "Get effort by name. Usage: effort <name>",
        "ids":      "List all task IDs",
        "find":     "Search task titles. Usage: find <substring>",
        "detail":   "Full detail for a task. Usage: detail <id>",
        "quit":     "Exit",
    }

    while True:
        try:
            line = input("vault-mcp> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue

        parts = line.split()
        cmd = parts[0].lower()

        if cmd == "quit" or cmd == "exit":
            break

        elif cmd == "help":
            for k, v in commands.items():
                print(f"  {k:12s} {v}")

        elif cmd == "status":
            print(json.dumps(cache.status(), indent=2, default=str))

        elif cmd == "tasks":
            kwargs = {}
            for arg in parts[1:]:
                if "=" in arg:
                    k, v = arg.split("=", 1)
                    if k == "limit":
                        kwargs[k] = int(v)
                    elif k in ("stub", "blocked", "include_subtasks"):
                        kwargs[k] = v.lower() in ("true", "1", "yes")
                    else:
                        kwargs[k] = v
            results = cache.query_tasks(**kwargs)
            print(f"Found {len(results)} tasks:")
            for t in results:
                tags_str = " ".join(f"{k}={v}" for k, v in t.tags.items() if k != "id" and v)
                indent = "  " * t.indent_level
                children_info = f" [{len(t.children)} sub]" if t.children else ""
                print(f"  {indent}[{t.status:12s}] {t.id or '???':10s} {t.title}{children_info}  {tags_str}")

        elif cmd == "task":
            if len(parts) < 2:
                print("Usage: task <id>")
                continue
            entry = cache.get_task(parts[1])
            if entry:
                t, path = entry
                print(f"  ID:       {t.id}")
                print(f"  Title:    {t.title}")
                print(f"  Status:   {t.status}")
                print(f"  Section:  {t.section}")
                print(f"  Indent:   {t.indent_level}")
                print(f"  Stub:     {t.is_stub}")
                print(f"  Blocked:  {t.is_blocked}")
                print(f"  Atomic:   {t.is_atomic}")
                print(f"  Tags:     {t.tags}")
                print(f"  Notes:    {t.notes}")
                print(f"  Children: {len(t.children)}")
                if t.children:
                    for c in t.children:
                        print(f"            [{c.id}] {c.title}")
                print(f"  File:     {path}")
            else:
                print(f"  Task '{parts[1]}' not found")

        elif cmd == "detail":
            if len(parts) < 2:
                print("Usage: detail <id>")
                continue
            entry = cache.get_task(parts[1])
            if entry:
                t, path = entry
                print(json.dumps({
                    "id": t.id,
                    "title": t.title,
                    "status": t.status,
                    "section": t.section,
                    "indent_level": t.indent_level,
                    "is_stub": t.is_stub,
                    "is_blocked": t.is_blocked,
                    "is_atomic": t.is_atomic,
                    "tags": t.tags,
                    "notes": t.notes,
                    "children": [c.id for c in t.children],
                    "file": str(path),
                }, indent=2))
            else:
                print(f"  Task '{parts[1]}' not found")

        elif cmd == "efforts":
            status_filter = None
            if len(parts) > 1 and "=" in parts[1]:
                _, status_filter = parts[1].split("=", 1)
            results = cache.list_efforts(status=status_filter)
            print(f"Found {len(results)} efforts:")
            for e in results:
                print(f"  {e.name:30s} status={e.status.value:8s} tasks={e.tasks_file or 'none'}")

        elif cmd == "effort":
            if len(parts) < 2:
                print("Usage: effort <name>")
                continue
            name = " ".join(parts[1:])
            e = cache.get_effort(name)
            if e:
                print(f"  Name:       {e.name}")
                print(f"  Status:     {e.status.value}")
                print(f"  Path:       {e.path}")
                print(f"  Tasks file: {e.tasks_file}")
                print(f"  Focused:    {e.is_focused}")
            else:
                print(f"  Effort '{name}' not found")

        elif cmd == "ids":
            all_ids = cache.get_all_task_ids()
            print(f"{len(all_ids)} task IDs:")
            for tid in sorted(all_ids):
                print(f"  {tid}")

        elif cmd == "find":
            if len(parts) < 2:
                print("Usage: find <substring>")
                continue
            needle = " ".join(parts[1:]).lower()
            all_tasks = cache.query_tasks(limit=9999)
            matches = [t for t in all_tasks if needle in t.title.lower()]
            print(f"Found {len(matches)} matching tasks:")
            for t in matches:
                print(f"  [{t.status:12s}] {t.id or '???':6s} {t.title}")

        else:
            print(f"Unknown command: {cmd}. Type 'help' for available commands.")


def main():
    if len(sys.argv) < 2:
        print("Usage: python harness.py <VAULT_ROOT> [--exclude .git,.obsidian]")
        sys.exit(1)

    vault_root = Path(sys.argv[1]).resolve()
    if not vault_root.is_dir():
        print(f"Error: {vault_root} is not a directory")
        sys.exit(1)

    exclude_dirs = {".git", ".obsidian", "node_modules", ".trash"}
    for i, arg in enumerate(sys.argv[2:]):
        if arg == "--exclude" and i + 1 < len(sys.argv) - 2:
            exclude_dirs = set(sys.argv[i + 3].split(","))

    print(f"Initializing cache from: {vault_root}")
    print(f"Exclude dirs: {exclude_dirs}")

    cache = VaultCache()
    cache.initialize(vault_root, exclude_dirs)

    smoke_test(cache)
    repl(cache)

    print("Done.")


if __name__ == "__main__":
    main()
