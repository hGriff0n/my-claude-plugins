"""Shared dependency: the single VaultCache instance."""

_cache = None


def set_cache(cache) -> None:
    global _cache
    _cache = cache


def get_cache():
    return _cache
