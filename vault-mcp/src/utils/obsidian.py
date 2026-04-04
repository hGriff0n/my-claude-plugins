import subprocess
import logging
import sys

log = logging.getLogger(__name__)

OBSIDIAN_EXE = "C:\\Users\\ghoop\\AppData\\Local\\Programs\\Obsidian\\Obsidian.com"

# Hide console windows on Windows
_SUBPROCESS_FLAGS = (
    subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
)

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
