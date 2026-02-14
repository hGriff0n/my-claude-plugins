#!/usr/bin/env python3
from pathlib import Path

VAULT_DIR = Path.home() / "clawd" / "efforts"

def get_effort_dir(name):
    """Get the directory path for an effort by name."""
    return VAULT_DIR / name
