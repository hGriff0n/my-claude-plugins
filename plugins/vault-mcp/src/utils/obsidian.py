import subprocess


def obsidian_cli(*args: str) -> subprocess.CompletedProcess:
    """Run an obsidian CLI command. Mockable in tests."""
    result = subprocess.run(["obsidian", *args], capture_output=True, text=True)
    if result.returncode == 0 and result.stdout.lstrip().startswith("Error:"):
        result.returncode = 1
        result.stderr = result.stdout.strip()
        result.stdout = ""
    return result
