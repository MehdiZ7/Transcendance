from datetime import UTC, date, datetime, timedelta

ONLINE_WINDOW = timedelta(minutes=5)

_last_seen: dict[int, datetime] = {}
_peak_day: date = date.min
_peak: int = 0


def touch(user_id: int) -> None:
    """Record that user_id just made an authenticated request"""
    _last_seen[user_id] = datetime.now(UTC)


def online_user_ids() -> list[int]:
    """Ids seen within ONLINE_WINDOW
    Prunes stale entries on the way, keeping the dict from growing indefinitely
	"""
    cutoff = datetime.now(UTC) - ONLINE_WINDOW
    for user_id, seen in list(_last_seen.items()):
        if seen < cutoff:
            del _last_seen[user_id]
    return list(_last_seen)


def record_peak(total: int, today: date) -> int:
    """Highest total observed today, reset when changing day
    only measured every timedelta
    """
    global _peak_day, _peak
    if today != _peak_day:
        _peak_day, _peak = today, 0
    _peak = max(_peak, total)
    return _peak


def reset() -> None:
    """Test helper: drop all state"""
    global _peak_day, _peak
    _last_seen.clear()
    _peak_day = date.min
    _peak = 0
