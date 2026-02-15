---
name: effort-workflow
description: Manage effort project workspaces and focus state. Use when the user issues `/effort-workflow:*` commands, queries for the current focus, or asks to create, focus, activate, backlog, list, or scan efforts.
---
# Effort Workflow

Manage "efforts" as dedicated project workspaces. Efforts are stored in the `efforts/` directory relative to the vault root (defined by `VAULT_ROOT` environment variable).

## Overview

Efforts are project workspaces that can be:
- **Active**: Currently being worked on
- **Backlog**: On hold or planned for future work
- **Focused**: One effort can be focused at a time for concentrated work

State is tracked in `~/.cache/efforts/efforts.json` with schema:
```json
{
  "focus": "effort-name",
  "active": ["effort-1", "effort-2"],
  "backlog": ["effort-3"]
}
```

### Session Model

Focusing, creating, or activating an effort **spawns a new Claude Code tab** (via `/windows:spawn-session`) with cwd set to the effort directory. Each tab owns its context naturally through cwd. The JSON focus field is kept for backwards compatibility when running from the vault root.

## Core Script

All commands use: `${CLAUDE_PLUGIN_ROOT}/scripts/efforts.py`

Python scripts print the effort directory path to stdout after state changes, which the command files use to pass to `/windows:spawn-session`.

## Commands

### Create New Effort

```bash
python efforts.py new <name>
```

Creates effort directory at `efforts/<name>` relative to vault root, initializes with README.md from template, marks active, and sets focus. Prints the effort directory path.

**Post-creation**: Invokes `/task-workflow:init <path>` with the effort directory, then spawns a new Claude Code tab in that directory via `/windows:spawn-session`.

**Quote names with spaces**: `python efforts.py new "My Project"`

### Get Current Focus

```bash
python efforts.py focus-get
```

Prints the name of the currently focused effort. Returns empty/null if no effort is focused.

**Use cases**:
- Determine current context before running other commands
- Integration with other skills that need to know the active effort
- Programmatic access to focus state

### Focus an Effort

```bash
python efforts.py focus <name>
```

Sets focus to an existing effort without changing its active/backlog status. Prints the effort directory path.

**Post-focus**: Spawns a new Claude Code tab in the effort directory via `/windows:spawn-session`.

**Fuzzy names**: If user provides partial name, confirm exact effort name before running.

### Unfocus (Shutdown Sequence)

```bash
python efforts.py focus <name> --unfocus
```

Unfocus is a **shutdown sequence** for the current effort session:
1. Resolves the effort name (from argument or current focus via `focus-get`)
2. Invokes `/daily:log` to record session progress
3. Clears the focus in the cache
4. Prints a message suggesting the user close the tab

There is no programmatic way to close a Windows Terminal tab, so the user must close it manually.

### Activate (Promote)

```bash
python efforts.py promote <name>
```

Moves effort from backlog to active and sets focus. Prints the effort directory path.

**Post-promote**: Spawns a new Claude Code tab in the effort directory via `/windows:spawn-session`.

**Fuzzy names**: Confirm exact effort name before running.

### Backlog (Relegate)

```bash
python efforts.py relegate <name>
```

Moves effort from active to backlog.

**Fuzzy names**: Confirm exact effort name before running.

### List Efforts

```bash
python efforts.py list [options]
```

**Options**:
- No args: Show active efforts only
- `--all` / `-a`: Show both active and backlog
- `--backlog` / `-b`: Show backlog only
- `--tasks` / `-t`: Show tasks (placeholder)

**Natural language mapping**:
- "show backlog projects" → `list --backlog`
- "what am I working on" → `list`
- "show all efforts" → `list --all`

### Scan and Rebuild

```bash
python efforts.py scan
```

Rebuilds state from filesystem by scanning `efforts/` directory relative to vault root:
- Directories with `README.md` → active
- Directories in `__backlog/` → backlog
- Files (not directories) → backlog
- Skips: `__ideas`, `dashboard.base`

Use when state file is corrupted or out of sync with filesystem.

## Effort Structure

Each effort directory contains:
- `README.md`: Required; initialized from `assets/readme.template.md`
- Additional files/folders as needed for the project

## Error Handling

- Effort must exist for focus/promote/relegate operations
- Script validates effort directory exists before state changes
- Use scan command to recover from state inconsistencies
