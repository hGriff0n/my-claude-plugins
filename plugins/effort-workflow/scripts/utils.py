#!/usr/bin/env python3
from pathlib import Path

def get_vault_root() -> Path:
    """Get vault root from VAULT_ROOT environment variable."""
    vault_root = os.environ.get('VAULT_ROOT')
    if not vault_root:
        print("ERROR: VAULT_ROOT environment variable not set.", file=sys.stderr)
        sys.exit(1)
    return Path(vault_root)


def get_effort_dir():
    return get_vault_root() / "efforts"
