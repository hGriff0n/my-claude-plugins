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

- **`effort_list`** — List efforts with optional status filter and task counts
- **`effort_get`** — Get effort details including task counts by status
- **`effort_create`** — Create a new effort directory, initialize files, and register it as active. Returns the effort `path`.
- **`effort_move`** — Move an effort between statuses (`active` / `backlog`). Handles filesystem move and cache refresh. Returns the effort `path`.
- **`effort_focus`** — Set the focused effort
- **`effort_scan`** — Re-scan the efforts directory to discover changes

## Commands

### Create New Effort

Calls `effort_create` with the effort name, which creates the directory and initializes CLAUDE.md, `00 README.md` and `01 TASKS.md` from templates. Then spawns a new Claude Code tab via `/windows:spawn-session`.

**Quote names with spaces**: Use quotes around multi-word names.

### Focus an Effort

Resolves the effort name via `effort_list` (for fuzzy matching), then spawns a new Claude Code tab via `/windows:spawn-session`.

**Fuzzy names**: If user provides partial name, use `effort_list` to confirm exact effort name and path first.

### Activate (Promote)

Calls `effort_move` with `status="active"` to move the effort from backlog to active. Then spawns a new Claude Code tab via `/windows:spawn-session`.

### Backlog (Relegate)

Calls `effort_move` with `status="backlog"` to move the effort from active to the backlog.

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
- `CLAUDE.md`: Required marker file (initialized from vault templates)
- `00 README.md`: Project overview (initialized from vault templates)
- `01 TASKS.md`: Task tracking (initialized from vault templates)
- Additional files/folders as needed for the project

## Error Handling

- Effort must exist in cache for focus/activate/backlog operations
- Use `effort_list` to verify effort names before operations
- Use scan command to recover from state inconsistencies after manual filesystem changes
