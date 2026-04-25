import subprocess
import logging
import sys
from typing import List

log = logging.getLogger(__name__)

OBSIDIAN_EXE = "C:\\Users\\ghoop\\AppData\\Local\\Programs\\Obsidian\\Obsidian.com"

# Hide console windows on Windows
_SUBPROCESS_FLAGS = (
    subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
)

# Stdout markers the CLI emits on successful command completion. The CLI
# can return rc=0 with empty stdout when its IPC to Obsidian silently
# fails (e.g. large content payloads exceeding the pipe-chunk size); for
# commands listed here we treat a missing marker as a failure.
_SUCCESS_MARKERS = {
    "append": "Appended to",
    "create": "Created:",
}

# Conservative chunk size for the CLI's content arg. Obsidian's main
# process reads each pipe chunk as a complete JSON message; large
# payloads split across OS pipe chunks crash with `Unexpected token ']'`
# or fail silently (rc=0, empty stdout). Empirically OK up to ~4KB; 2KB
# leaves headroom for path arg + envelope.
CONTENT_CHUNK_BYTES = 2000


def obsidian_cli(*args: str) -> subprocess.CompletedProcess:
    """Run an obsidian CLI command. Mockable in tests."""
    result = subprocess.run(
        [OBSIDIAN_EXE, *args],
        capture_output=True, text=True,
        creationflags=_SUBPROCESS_FLAGS,
    )
    log.info(f'Obsidian: {args} => {result}')
    if result.returncode == 0 and result.stdout.lstrip().startswith("Error:"):
        log.error(result.stdout)
        result.returncode = 1
        result.stderr = result.stdout.strip()
        result.stdout = ""
        return result

    expected = _SUCCESS_MARKERS.get(args[0]) if args else None
    if result.returncode == 0 and expected and expected not in result.stdout:
        log.error("Obsidian CLI silent failure (no %r in stdout): %r",
                  expected, result.stdout)
        result.returncode = 1
        result.stderr = (
            f"Obsidian CLI returned rc=0 without success marker "
            f"{expected!r}: stdout={result.stdout!r}"
        )
        result.stdout = ""
    return result


def split_on_line_boundaries(content: str, max_bytes: int) -> List[str]:
    """Split content into chunks <= max_bytes, breaking only on newlines."""
    chunks: List[str] = []
    current: List[str] = []
    current_size = 0
    for line in content.split("\n"):
        line_size = len(line.encode("utf-8")) + 1  # +1 for the rejoining \n
        if current and current_size + line_size > max_bytes:
            chunks.append("\n".join(current))
            current = [line]
            current_size = line_size
        else:
            current.append(line)
            current_size += line_size
    if current:
        chunks.append("\n".join(current))
    return chunks
