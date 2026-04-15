"""Shared dependency: the single VaultCache instance."""

from fastapi import HTTPException

_cache = None


def set_cache(cache) -> None:
    global _cache
    _cache = cache


def get_cache():
    if _cache is None:
        raise HTTPException(
            status_code=503,
            detail="Vault not initialized: Obsidian is not running or no vault is open. "
                   "Start Obsidian and retry.",
        )
    return _cache
