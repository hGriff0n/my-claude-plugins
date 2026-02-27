# vault-mcp

A dockerized MCP server providing fast, cached access to vault tasks and efforts.

## Features

- In-process cache of all `TASKS.md` files across the vault — no per-request file parsing
- In-memory SQLite index for efficient filtered queries (by status, effort, due date, etc.)
- Background file watcher that auto-refreshes the cache when files change
- Full task and effort management via MCP tools
- Lossless write-back: the in-memory model captures all task semantics; `formatting.py` defines the canonical tag rendering format

## MCP Tools

### Task Tools
| Tool | Description |
|------|-------------|
| `task_list` | Filter tasks: status, effort, due, stub, blocked, atomic |
| `task_get` | Get single task by ID |
| `task_add` | Add new task with auto-generated ID |
| `task_update` | Update task metadata |
| `task_blockers` | Show upstream/downstream blocking relationships |
| `cache_status` | Show cache statistics |

### Effort Tools
| Tool | Description |
|------|-------------|
| `effort_list` | List efforts by status |
| `effort_get` | Get effort details + task summary |
| `effort_focus` | Set focused effort |
| `effort_get_focus` | Get current focused effort |
| `effort_activate` | Move effort to active |
| `effort_backlog` | Move effort to backlog |
| `effort_scan` | Rebuild effort state from filesystem |

## Setup

### Docker

```bash
docker build -t vault-mcp .
```

### Claude Code Integration

Add to your `~/.claude/mcp.json` or project `.mcp.json`:

```json
{
  "mcpServers": {
    "vault": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-v", "/path/to/your/vault:/vault:rw",
        "-e", "VAULT_ROOT=/vault",
        "vault-mcp"
      ]
    }
  }
}
```

## Configuration

| Environment Variable | Default | Description |
|----------------------|---------|-------------|
| `VAULT_ROOT` | (required) | Path to vault directory |
| `EXCLUDE_DIRS` | `.git,.obsidian,node_modules,.trash` | Comma-separated dir names to skip |

## Architecture

- `src/models/` — Task and Effort dataclasses
- `src/parsers/` — TASKS.md parser and effort directory scanner
- `src/cache/` — Thread-safe in-memory cache with SQLite metadata index
- `src/watcher/` — watchdog-based file system watcher
- `src/tools/` — MCP tool handler implementations
- `src/utils/` — Date parsing, ID generation, canonical tag formatting
- `src/server.py` — MCP server entry point
