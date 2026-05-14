# Logging

## Overview

The server logs to both `stderr` and a timestamped file under `logs/`. Files rotate daily at midnight, keeping 14 days of history.

## Stream Fallback

Before configuring logging, replace `sys.stderr` and `sys.stdout` with `os.devnull` if either is `None`. This handles environments (e.g. `pythonw`, detached processes, certain MCP launchers) where the standard streams are not attached.

```python
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
```

## Log Directory

Logs are written to a `logs/` directory at the project root (one level above `src/`):

```python
_log_dir = Path(__file__).resolve().parent.parent / "logs"
_log_dir.mkdir(exist_ok=True)
```

The directory is created on import if it does not already exist.

## Log File Naming

Each server start creates a new log file named with the current timestamp:

```python
_log_file = _log_dir / f"server_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
```

Format: `server_YYYY-MM-DD_HH-MM-SS.log`

## Configuration

Configured once at module import via `logging.basicConfig`:

- **Level:** `INFO`
- **Format:** `%(asctime)s %(levelname)s %(name)s: %(message)s`
- **Handlers:**
  - `StreamHandler(sys.stderr)` — only attached if `sys.stderr` is truthy after the fallback above
  - `TimedRotatingFileHandler` — rotates at midnight (`when="midnight"`), retains 14 backups

```python
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        h for h in [
            logging.StreamHandler(sys.stderr) if sys.stderr else None,
            logging.handlers.TimedRotatingFileHandler(
                _log_file, when="midnight", backupCount=14,
            ),
        ] if h is not None
    ],
)
log = logging.getLogger(__name__)
```

The handler list filters out `None` entries so the stream handler is omitted cleanly when `stderr` is unavailable.

## Module Logger

Each module obtains its own logger via `logging.getLogger(__name__)`. The module name appears in every log line via the `%(name)s` format token, making it easy to trace which subsystem produced a given message.
