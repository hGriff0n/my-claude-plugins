#!/usr/bin/env python3
"""
Spawn a new Claude Code session in Windows Terminal.

Usage:
    python spawn_session.py <directory> [--split]

Arguments:
    directory: Directory to launch Claude in (required)
    --split: Use split pane instead of new tab (optional)
"""

import argparse
import subprocess
import sys
from pathlib import Path


def spawn_claude_session(directory: str, split_pane: bool = False) -> None:
    """
    Spawn a new Claude Code session in Windows Terminal.

    Args:
        directory: Directory path to launch Claude in
        split_pane: If True, use split pane; otherwise use new tab
    """
    # Validate directory exists
    dir_path = Path(directory).resolve()
    if not dir_path.exists():
        print(f"Error: Directory does not exist: {dir_path}", file=sys.stderr)
        sys.exit(1)

    if not dir_path.is_dir():
        print(f"Error: Path is not a directory: {dir_path}", file=sys.stderr)
        sys.exit(1)

    # Construct Windows Terminal command
    # wt -w 0 nt -d <dir> -p <profile>  (new tab)
    # wt -w 0 sp -d <dir> -p <profile>  (split pane)
    # Uses the "claudeclone" Windows Terminal profile to launch Claude

    mode = "sp" if split_pane else "nt"
    cmd = ["wt", "-w", "0", mode, "-d", str(dir_path), "-p", "claudeclone"]

    try:
        # Execute the command
        subprocess.run(cmd, check=True)
        pane_type = "split pane" if split_pane else "new tab"
        print(f"Success: Spawned Claude Code session in {pane_type}: {dir_path}")
    except subprocess.CalledProcessError as e:
        print(f"Error: Failed to spawn session: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print("Error: Windows Terminal 'wt' command not found. Is Windows Terminal installed?", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Spawn a new Claude Code session in Windows Terminal"
    )
    parser.add_argument(
        "directory",
        help="Directory to launch Claude in"
    )
    parser.add_argument(
        "--split",
        action="store_true",
        help="Use split pane instead of new tab"
    )

    args = parser.parse_args()
    spawn_claude_session(args.directory, args.split)


if __name__ == "__main__":
    main()
