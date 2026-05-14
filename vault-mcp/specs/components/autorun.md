# Autorun

## Overview

The vault-mcp server is launched at user login by a Windows Task Scheduler job that runs `startup.bat` from the project root. The batch file launches the server detached via `pythonw.exe` so it has no console window, and skips launching when an instance is already serving on the configured port.

Paths shown below are machine-specific examples from the development setup; replace them per machine when reproducing.

## startup.bat

Lives at the project root (`my-vault/vault-mcp/startup.bat`). Responsibilities:

1. Probe the server's MCP endpoint on the loopback address.
2. If the probe shows the server is already running, exit without launching.
3. Otherwise, launch `server.py` under `pythonw.exe` in a detached process.

### Running-server check

Use `curl` (shipped with Windows 10+) to hit `http://127.0.0.1:9400/mcp`. Decide based on `curl`'s exit code:

- **Exit code `7`** — "Failed to connect to host". The server is not running; proceed to launch.
- **Any other exit code** (including success or an HTTP-level error) — something is bound to the port and answering; treat the server as already running and exit.

Use `--silent --output NUL --max-time 2` so the probe doesn't print to the console and can't hang the login sequence.

### Launch

`start ""` is used so `cmd` returns immediately without waiting on the child. The empty `""` is the window title argument required by `start` when the command path is quoted. `pythonw.exe` is used (not `python.exe`) to avoid spawning a console window.

```bat
@echo off
curl --silent --output NUL --max-time 2 http://127.0.0.1:9400/mcp
if %ERRORLEVEL%==7 (
    start "" C:\Users\ghoop\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe "C:\Users\ghoop\Desktop\claudecode\my-vault\vault-mcp\src\server.py"
)
```

The port (`9400`) must match the port `server.py` binds — see `specs/components/server.md`.

## Task Scheduler registration

The job is exported to `mcp-launch.xml` at the project root and can be re-imported via Task Scheduler's "Import Task..." action or `schtasks /create /xml mcp-launch.xml /tn "myvault\mcp-launch"`.

Settings that matter for reproducing the job:

- **Trigger:** `LogonTrigger` for the specific user — fires once per interactive logon of that account.
- **Principal:**
  - `LogonType: InteractiveToken` — runs in the user's interactive session, so the server inherits the desktop environment.
  - `RunLevel: LeastPrivilege` — no elevation; the server does not require admin rights.
- **Action:** single `Exec` invoking the absolute path to `startup.bat`. No arguments, no working directory override (the bat file uses absolute paths internally, so it doesn't depend on `cwd`).
- **MultipleInstancesPolicy: `IgnoreNew`** — if the task is already considered running, additional triggers are dropped. Belt-and-braces with the `curl` probe in `startup.bat`.
- **DisallowStartIfOnBatteries / StopIfGoingOnBatteries: `true`** — the server is desktop-only; don't drain a laptop battery if the user logs in unplugged.
- **StartWhenAvailable: `false`** — if the logon trigger is missed (e.g. machine off), don't try to catch up later. The next login will fire it.
- **AllowStartOnDemand: `true`** — lets the user run the task manually from Task Scheduler for testing.
- **ExecutionTimeLimit: `PT72H`** — Task Scheduler will hard-stop the task after 72 hours. Long enough to cover normal use; restart on next login.
- **AllowHardTerminate: `true`** — Task Scheduler may force-kill on stop. The server has no critical shutdown path, so this is safe.
- **Priority: `7`** — default "below normal" priority class for scheduled tasks; keeps the server out of the way of foreground work.

The `<Enabled>` flag inside `<Settings>` controls whether the task fires; toggle it via Task Scheduler's enable/disable rather than editing the XML.
