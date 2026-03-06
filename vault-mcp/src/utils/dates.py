"""
Date and duration parsing utilities.

Adapted from task-workflow/scripts/utils.py — pure functions, no external dependencies.
"""

import re
from datetime import datetime, timedelta
from typing import Optional


def parse_date(date_str: str) -> Optional[str]:
    """
    Parse various date formats into ISO 8601 (YYYY-MM-DD).

    Supports:
    - ISO 8601: "2026-02-15"
    - Natural language: "today", "tomorrow", "Friday", "next Monday"
    - Relative: "in 3 days", "in 2 weeks"
    - Prose prefixes: "before March 15", "by Friday", "due Friday"
    - Urgency: "ASAP", "immediately", "urgent"

    Returns:
        ISO 8601 date string or None if unparseable
    """
    if not date_str:
        return None

    date_str = date_str.strip()
    today = datetime.now().date()

    if date_str.lower() in ("asap", "immediately", "urgent", "now"):
        return today.isoformat()
    if date_str.lower() == "today":
        return today.isoformat()
    if date_str.lower() == "tomorrow":
        return (today + timedelta(days=1)).isoformat()

    for prefix in ("before ", "by ", "due ", "on "):
        if date_str.lower().startswith(prefix):
            date_str = date_str[len(prefix):].strip()

    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date().isoformat()
    except ValueError:
        pass

    for fmt in ("%B %d", "%b %d", "%m/%d", "%m-%d", "%B %d, %Y", "%b %d, %Y"):
        try:
            parsed = datetime.strptime(date_str, fmt).date()
            if parsed.year == 1900:
                parsed = parsed.replace(year=today.year)
                if parsed < today:
                    parsed = parsed.replace(year=today.year + 1)
            return parsed.isoformat()
        except ValueError:
            continue

    day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    date_lower = date_str.lower()
    is_next = date_lower.startswith("next ")
    if is_next:
        date_lower = date_lower[5:].strip()

    for i, day_name in enumerate(day_names):
        if date_lower == day_name:
            days_ahead = i - today.weekday()
            if days_ahead <= 0 or is_next:
                days_ahead += 7
            return (today + timedelta(days=days_ahead)).isoformat()

    relative_match = re.match(r'in (\d+) (days?|weeks?)', date_lower)
    if relative_match:
        amount = int(relative_match.group(1))
        unit = relative_match.group(2)
        delta = timedelta(weeks=amount) if unit.startswith("week") else timedelta(days=amount)
        return (today + delta).isoformat()

    return None


def duration_to_minutes(duration_str: str) -> Optional[int]:
    """
    Parse duration string into total minutes.

    Supports: "2h", "30m", "2d", "2h30m", "2.5h", "2 hours", "45 minutes"
    """
    if not duration_str:
        return None

    s = duration_str.strip().lower()
    total = 0

    days = re.search(r'(\d+(?:\.\d+)?)\s*(?:d|days?)', s)
    if days:
        total += int(float(days.group(1)) * 24 * 60)

    hours = re.search(r'(\d+(?:\.\d+)?)\s*(?:h|hours?)', s)
    if hours:
        total += int(float(hours.group(1)) * 60)

    minutes = re.search(r'(\d+)\s*(?:m|mins?|minutes?)', s)
    if minutes:
        total += int(minutes.group(1))

    return total if total > 0 else None


def minutes_to_duration(total_minutes: int) -> Optional[str]:
    """Format minutes as a compact duration string (e.g. "2h30m", "3d")."""
    if not total_minutes:
        return None

    days, remainder = divmod(total_minutes, 24 * 60)
    hours, mins = divmod(remainder, 60)

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if mins:
        parts.append(f"{mins}m")

    return "".join(parts) if parts else None


def parse_duration(duration_str: str) -> Optional[str]:
    """
    Parse duration string into normalized compact format.

    "2 hours 30 minutes" → "2h30m", "2.5h" → "2h30m"
    """
    total = duration_to_minutes(duration_str)
    if total is None:
        return None
    return minutes_to_duration(total)
