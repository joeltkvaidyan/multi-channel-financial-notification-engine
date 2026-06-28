"""
TRAI DND (Do Not Disturb) compliance.

India's TRAI DND regulation under TCCCPR 2018 restricts PROMOTIONAL
communication to numbers registered on the National DND registry, and
restricts the hours during which promotional commercial messages may be
sent (09:00-21:00 IST).

Crucially: DND restrictions apply ONLY to PROMOTIONAL traffic.
TRANSACTIONAL messages (OTPs, order confirmations, margin calls, payment
failures) are exempt — this is exactly why `Classification` is the first
gate the compliance layer checks. Getting this distinction wrong either
(a) blocks legally-required regulatory alerts, or (b) spams DND-registered
numbers with marketing and exposes the business to TRAI penalties.
"""

from __future__ import annotations

from datetime import datetime, time

from app.domain.event_types import Classification, EventTypeSpec

# TRAI-mandated promotional sending window (local time)
PROMOTIONAL_WINDOW_START = time(9, 0)
PROMOTIONAL_WINDOW_END = time(21, 0)


def is_dnd_blocked(spec: EventTypeSpec, dnd_registered: bool, now: datetime | None = None) -> tuple[bool, str | None]:
    """Returns (blocked, reason). Transactional traffic is never DND-blocked."""
    if spec.classification == Classification.TRANSACTIONAL:
        return False, None

    if not dnd_registered:
        return False, None

    # DND-registered number + promotional content -> block on SMS/voice channels.
    # (Email/push/WhatsApp opt-in are governed by user preference, not TRAI DND,
    # but we still respect the promotional sending window for all channels as
    # a fatigue-prevention measure, not a strict legal requirement.)
    return True, "TRAI_DND_REGISTERED_PROMOTIONAL_BLOCKED"


def is_outside_promotional_window(now: datetime | None = None) -> bool:
    now = now or datetime.now()
    current = now.time()
    return not (PROMOTIONAL_WINDOW_START <= current <= PROMOTIONAL_WINDOW_END)


def check_trai_compliance(
    spec: EventTypeSpec, dnd_registered: bool, now: datetime | None = None
) -> tuple[bool, str | None]:
    """Single entry point the compliance layer calls.

    Returns (allowed, suppression_reason).
    """
    blocked, reason = is_dnd_blocked(spec, dnd_registered, now)
    if blocked:
        return False, reason

    if spec.classification == Classification.PROMOTIONAL and is_outside_promotional_window(now):
        return False, "OUTSIDE_TRAI_PROMOTIONAL_WINDOW"

    return True, None
