---
name: effort-workflow
description: Manage effort project workspaces and focus state. Use when the user issues `/effort-workflow:*` commands, queries for the current focus, or asks to create, focus, activate, backlog, list, or scan efforts.
---
# Effort Workflow

Manage "efforts" as dedicated project workspaces. Efforts are stored in the `efforts/` directory relative to the vault root (defined by `VAULT_ROOT` environment variable).

## Overview

Efforts are project workspaces that can be:
- **Active**: Top-level directories under `efforts/` with a `CLAUDE.md` marker file
- **Backlog**: Directories under `efforts/__backlog/` with a `CLAUDE.md` marker file
- **Focused**: One effort can be focused at a time for concentrated work

Status is derived from directory structure — the vault-mcp server scans `efforts/` to discover efforts and their status. Focus state is managed in-memory by the MCP server.

### Session Model

Focusing, creating, or activating an effort **spawns a new Claude Code tab** (via `/windows:spawn-session`) with cwd set to the effort directory. Each tab owns its context naturally through cwd.

## MCP Tools (vault-mcp server)

Most effort operations use the vault-mcp MCP server:

- **`effort_list`** — List efforts with optional status filter and task counts
- **`effort_get`** — Get effort details including task counts by status
- **`effort_focus`** — Set the focused effort
- **`effort_unfocus`** — Clear the current focus
- **`effort_get_focus`** — Get the focused effort and its open tasks
- **`effort_scan`** — Re-scan the efforts directory to discover changes

## Commands

### Create New Effort

Creates effort directory at `efforts/<name>`, writes CLAUDE.md and README.md from templates, calls `effort_scan` to discover it, then `effort_focus` to focus it.

**Post-creation**: Invokes `/task-workflow:init <path>` to create TASKS.md, then spawns a new Claude Code tab via `/windows:spawn-session`.

**Quote names with spaces**: Use quotes around multi-word names.

### Get Current Focus

Calls `effort_get_focus` MCP tool. Returns the focused effort name, path, and open tasks summary.

### Focus an Effort

Calls `effort_focus` MCP tool, then spawns a new Claude Code tab via `/windows:spawn-session`.

**Fuzzy names**: If user provides partial name, use `effort_list` to confirm exact effort name first.

### Unfocus (Shutdown Sequence)

Unfocus is a **shutdown sequence** for the current effort session:
1. Resolves the effort name (from argument or current focus via `effort_get_focus`)
2. Invokes `/daily:log` to record session progress
3. Calls `effort_unfocus` MCP tool to clear focus
4. Prints a message suggesting the user close the tab
5. Invokes `/quit` to exit Claude

### Activate (Promote)

Moves effort from backlog to active by relocating the directory from `efforts/__backlog/<name>` to `efforts/<name>`, then calls `effort_scan` and `effort_focus`.

**Post-activate**: Spawns a new Claude Code tab via `/windows:spawn-session`.

### Backlog (Relegate)

Moves effort from active to backlog by relocating the directory from `efforts/<name>` to `efforts/__backlog/<name>`, then calls `effort_scan`.

### List Efforts

Calls `effort_list` MCP tool with optional filters:
- No args: Show active efforts only (`status="active"`)
- `--all` / `-a`: Show both active and backlog (omit status filter)
- `--backlog` / `-b`: Show backlog only (`status="backlog"`)
- `--tasks` / `-t`: Include task counts (`include_task_counts=true`)

### Scan and Rebuild

Calls `effort_scan` MCP tool to re-scan the `efforts/` directory:
- Top-level directories with `CLAUDE.md` → active
- Directories under `__backlog/` with `CLAUDE.md` → backlog (recursive)
- Skips: `__ideas`, `dashboard.base`

Use when directories have been manually moved or created.

## Effort Structure

Each effort directory contains:
- `CLAUDE.md`: Required marker file (initialized from `assets/CLAUDE.template.md`)
- `README.md`: Project overview (initialized from `assets/readme.template.md`)
- `TASKS.md`: Task tracking (created via `/task-workflow:init`)
- Additional files/folders as needed for the project

## Error Handling

- Effort must exist in cache for focus/activate/backlog operations
- Use `effort_list` to verify effort names before operations
- Use scan command to recover from state inconsistencies after manual filesystem changes
