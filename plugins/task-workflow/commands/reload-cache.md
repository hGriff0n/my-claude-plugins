---
description: Show vault cache status and diagnostics
allowed-tools: mcp__vault-mcp__cache_status
---

Show the current vault cache status using the `cache_status` MCP tool.

The vault-mcp server automatically watches for file changes and refreshes its cache. Manual cache rebuilds are no longer needed.

Call the `cache_status` MCP tool (no parameters) and report:
- Number of files indexed
- Number of tasks indexed
- Number of efforts indexed
- Last full scan timestamp
