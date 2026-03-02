import subprocess


def obsidian_cli(*args: str) -> subprocess.CompletedProcess:
    """Run an obsidian CLI command. Mockable in tests."""
    return subprocess.run(["obsidian", *args], capture_output=True, text=True)
