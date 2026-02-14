---
name: spawn-session
description: "Spawn new Claude Code sessions in Windows Terminal tabs or split panes. Use when: (1) User explicitly requests spawning a new session, new tab, or split pane, (2) Suggesting the user switch to work on a different effort in parallel, (3) Recommending multi-session workflows where different tasks should run concurrently, (4) User mentions opening Claude in another window/tab/pane. Supports specifying target directories for the new session."
---

# Spawn Session

Spawn new Claude Code instances in Windows Terminal, either as new tabs or split panes.

## Usage

### Basic Pattern

When the user requests a new Claude session, use the bundled `spawn_session.py` script:

```bash
python scripts/spawn_session.py <directory>
```

This spawns a new tab by default. For a split pane:

```bash
python scripts/spawn_session.py <directory> --split
```

### When to Use This Skill

Trigger this skill in these scenarios:

1. **Explicit spawn requests**: User says "spawn a new session", "open claude in a new tab", "split pane", etc.
2. **Effort switching**: When suggesting the user work on a different effort, offer to spawn a session in that effort's directory
3. **Multi-session workflows**: When recommending parallel work (e.g., "open a session for the tutoring effort while I work on this")
4. **Context switching**: User wants to work in a different directory without closing current session

### Parameters

- **directory** (required): Full path to the directory where Claude should start
  - Must be an existing directory
  - Use absolute paths for clarity
  - Common patterns: effort directories, vault root, specific project folders

- **--split** (optional): Use split pane instead of new tab
  - Default: new tab
  - Only include when user explicitly requests split pane

### Examples

Spawn in an effort directory (new tab):
```bash
python scripts/spawn_session.py "C:\Users\ghoop\Desktop\my-brain\efforts\workflow"
```

Spawn in vault root (split pane):
```bash
python scripts/spawn_session.py "C:\Users\ghoop\Desktop\my-brain" --split
```

Spawn in a project directory:
```bash
python scripts/spawn_session.py "C:\Users\ghoop\projects\my-app"
```

## Workflow Patterns

### Effort Switching

When discussing effort switching:
```
User: "I want to work on the french effort now"
Claude: "I can spawn a new Claude session in the french effort directory.
         Would you like me to open it in a new tab or split pane?"
```

Then execute:
```bash
python scripts/spawn_session.py "C:\Users\ghoop\Desktop\my-brain\efforts\french"
```

### Parallel Work

When recommending multi-session workflows:
```
User: "Can you help me practice French while also working on my workflow tasks?"
Claude: "I recommend using two separate Claude sessions for this. Let me spawn
         a new session in the french effort directory for practice."
```

### Split Pane vs New Tab

**Default to new tab** unless the user explicitly requests a split pane. New tabs provide:
- More screen space
- Clearer separation between sessions
- Easier context switching via tab bar

Use split panes when:
- User explicitly requests it
- User wants to see both sessions simultaneously
- Working on related tasks that benefit from side-by-side view

## Error Handling

The script validates the directory before spawning:
- Non-existent directories: Error message with path
- Non-directory paths: Error message
- Missing Windows Terminal: Clear error about 'wt' command

If the script fails, verify:
1. Directory path is correct and exists
2. Windows Terminal is installed
3. Path uses forward slashes or escaped backslashes

## Implementation Notes

- Uses `wt -w 0 nt -d <dir> -p claudeclone` for new tabs
- Uses `wt -w 0 sp -d <dir> -p claudeclone` for split panes
- `-w 0` targets the current Windows Terminal window
- `nt` = new tab, `sp` = split pane
- `-p claudeclone` uses the "claudeclone" Windows Terminal profile
- Script resolves paths to absolute before execution

## Requirements

This skill requires a Windows Terminal profile named "claudeclone" that launches Claude Code. The profile should be configured in the Windows Terminal settings to run Claude without resource sharing conflicts.
