"""
Task ID generation utilities.
"""

import secrets


def generate_task_id(length: int = 6) -> str:
    """
    Generate a cryptographically random hex task ID.

    Args:
        length: Length of the ID in hex characters (default 6)

    Returns:
        Lowercase hex string, e.g. "a7f3c2"
    """
    return secrets.token_hex((length + 1) // 2)[:length]
