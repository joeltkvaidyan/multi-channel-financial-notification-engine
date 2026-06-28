"""
Frequency capping.

Quiet hours stop notifications at the wrong TIME; frequency capping stops
too MANY notifications regardless of time. Both exist to prevent fatigue,
but they're independent controls — a user could have no quiet hours set
yet still want "max 3 promotional messages a day".

Caps apply to PROMOTIONAL traffic only by default. Capping TRANSACTIONAL
alerts (a margin call, a failed payment) would mean a user literally
doesn't find out their position is at risk because they "used up" their
daily quota on something else — that's a real-money/compliance failure,
so transactional messages are never capped here.
"""

from __future__ import annotations

from datetime import date

from app.domain.event_types import Classification, EventTypeSpec


class FrequencyCapTracker:
    """In-memory per-user, per-day counters. In production this would be a
    Redis key with a 24h TTL (INCR + EXPIRE) shared across app instances —
    kept as a plain dict here to avoid adding infra to the demo."""

    def __init__(self) -> None:
        self._counts: dict[tuple[str, str], int] = {}

    def _key(self, user_id: str, day: date) -> tuple[str, str]:
        return (user_id, day.isoformat())

    def increment_and_get(self, user_id: str, day: date) -> int:
        key = self._key(user_id, day)
        self._counts[key] = self._counts.get(key, 0) + 1
        return self._counts[key]

    def current_count(self, user_id: str, day: date) -> int:
        return self._counts.get(self._key(user_id, day), 0)


_tracker = FrequencyCapTracker()


def get_tracker() -> FrequencyCapTracker:
    return _tracker


def exceeds_cap(spec: EventTypeSpec, user_id: str, max_per_day: int, today: date | None = None) -> bool:
    if spec.classification != Classification.PROMOTIONAL:
        return False
    today = today or date.today()
    current = _tracker.current_count(user_id, today)
    return current >= max_per_day


def record_send(spec: EventTypeSpec, user_id: str, today: date | None = None) -> None:
    if spec.classification != Classification.PROMOTIONAL:
        return
    _tracker.increment_and_get(user_id, today or date.today())
