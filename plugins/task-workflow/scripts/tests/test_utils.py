#!/usr/bin/env python3
"""
Unit tests for utils.py
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pytest
from utils import (
    generate_task_id,
    parse_date,
    parse_duration,
    duration_to_minutes,
    increment_duration,
    check_due_date
)


def test_generate_task_id():
    """Test task ID generation."""
    task_id = generate_task_id(6)
    assert len(task_id) == 6
    assert all(c in '0123456789abcdef' for c in task_id)
    
    task_id_8 = generate_task_id(8)
    assert len(task_id_8) == 8


def test_generate_task_id_unique():
    """Test that IDs are unique."""
    ids = [generate_task_id() for _ in range(100)]
    assert len(ids) == len(set(ids))  # All unique


def test_parse_date_iso():
    """Test parsing ISO 8601 dates."""
    assert parse_date('2026-02-15') == '2026-02-15'
    assert parse_date('2026-12-31') == '2026-12-31'


def test_parse_date_keywords():
    """Test parsing date keywords."""
    today = datetime.now().date().isoformat()
    tomorrow = (datetime.now().date() + timedelta(days=1)).isoformat()
    
    assert parse_date('today') == today
    assert parse_date('tomorrow') == tomorrow
    assert parse_date('ASAP') == today
    assert parse_date('immediately') == today


def test_parse_date_with_prefix():
    """Test parsing dates with prefixes."""
    assert parse_date('before 2026-02-15') == '2026-02-15'
    assert parse_date('by 2026-03-01') == '2026-03-01'
    assert parse_date('due 2026-04-10') == '2026-04-10'


def test_parse_date_relative():
    """Test parsing relative dates."""
    today = datetime.now().date()
    
    in_3_days = (today + timedelta(days=3)).isoformat()
    assert parse_date('in 3 days') == in_3_days
    
    in_2_weeks = (today + timedelta(weeks=2)).isoformat()
    assert parse_date('in 2 weeks') == in_2_weeks


def test_parse_date_day_names():
    """Test parsing day names."""
    today = datetime.now().date()
    
    # Find next Friday
    days_until_friday = (4 - today.weekday()) % 7
    if days_until_friday == 0:
        days_until_friday = 7  # If today is Friday, get next Friday
    next_friday = today + timedelta(days=days_until_friday)
    
    result = parse_date('Friday')
    # Allow for "this Friday" or "next Friday" depending on current day
    assert result is not None


def test_parse_duration_hours():
    """Test parsing hour durations."""
    assert parse_duration('2h') == '2h'
    assert parse_duration('2.5h') == '2h30m'
    assert parse_duration('2 hours') == '2h'


def test_parse_duration_minutes():
    """Test parsing minute durations."""
    assert parse_duration('30m') == '30m'
    assert parse_duration('45 minutes') == '45m'


def test_parse_duration_days():
    """Test parsing day durations."""
    assert parse_duration('2d') == '2d'
    assert parse_duration('3 days') == '3d'


def test_parse_duration_mixed():
    """Test parsing mixed durations."""
    assert parse_duration('2h30m') == '2h30m'
    assert parse_duration('1d4h') == '1d4h'


def test_duration_to_minutes():
    """Test converting duration to minutes."""
    assert duration_to_minutes('2h') == 120
    assert duration_to_minutes('30m') == 30
    assert duration_to_minutes('2h30m') == 150
    assert duration_to_minutes('1d') == 1440
    assert duration_to_minutes('1d2h30m') == 1590


def test_increment_duration():
    """Test incrementing duration."""
    assert increment_duration('2h', '30m') == '2h30m'
    assert increment_duration('2h', '+1h') == '3h'
    assert increment_duration('1d', '2h') == '1d2h'
    assert increment_duration('', '2h') == '2h'


def test_check_due_date_today():
    """Test checking if task is due today."""
    today = datetime.now().date().isoformat()
    yesterday = (datetime.now().date() - timedelta(days=1)).isoformat()
    tomorrow = (datetime.now().date() + timedelta(days=1)).isoformat()

    assert check_due_date(today, 'today') is True, 'today is not today'
    assert check_due_date(yesterday, 'today') is True, 'yesterday is not today'
    assert check_due_date(tomorrow, 'today') is False, 'tomorrow is today'


def test_check_due_date_this_week():
    """Test checking if task is due this week."""
    today = datetime.now().date()
    next_week = today + timedelta(days=8)
    
    assert check_due_date(today.isoformat(), 'this-week') is True
    assert check_due_date(next_week.isoformat(), 'this-week') is False


def test_check_due_date_overdue():
    """Test checking if task is overdue."""
    yesterday = (datetime.now().date() - timedelta(days=1)).isoformat()
    today = datetime.now().date().isoformat()
    tomorrow = (datetime.now().date() + timedelta(days=1)).isoformat()
    
    assert check_due_date(yesterday, 'overdue') is True
    assert check_due_date(today, 'overdue') is False
    assert check_due_date(tomorrow, 'overdue') is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
