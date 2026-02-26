"""
Canonical tag formatting for task markdown serialization.

This module is the single source of truth for how each task tag is rendered
back to markdown. Changing a format here and running a normalize operation
will update all task files in the vault automatically.

Current canonical format:
- Emoji tags (Obsidian Tasks plugin compatible): id, due, scheduled, created, completed, b (blocked)
- Hashtag tags: estimate, actual, stub, routine, and any unknown tags
"""

from typing import Dict

# Emoji representations for Obsidian Tasks plugin compatibility.
# Tags in this mapping are rendered as: <emoji> <value>
TAG_TO_EMOJI: Dict[str, str] = {
    'id': '🆔',
    'due': '📅',
    'scheduled': '⏳',
    'created': '➕',
    'completed': '✅',
    'b': '⛔',
}

EMOJI_TO_TAG: Dict[str, str] = {v: k for k, v in TAG_TO_EMOJI.items()}


def render_tag(name: str, value: str) -> str:
    """
    Render a single tag to its canonical markdown representation.

    Args:
        name: Tag name (e.g. "due", "estimate", "stub")
        value: Tag value (empty string for flag-only tags like "stub")

    Returns:
        Canonical tag string (e.g. "📅 2026-02-15", "#estimate:4h", "#stub")
    """
    if name in TAG_TO_EMOJI:
        emoji = TAG_TO_EMOJI[name]
        return f"{emoji} {value}"
    if value:
        return f"#{name}:{value}"
    return f"#{name}"


def render_tags(tags: Dict[str, str]) -> str:
    """
    Render all tags to a space-separated string.

    Args:
        tags: Dict mapping tag names to values

    Returns:
        Space-separated string of rendered tags, or empty string if no tags
    """
    return " ".join(render_tag(name, value) for name, value in tags.items())
