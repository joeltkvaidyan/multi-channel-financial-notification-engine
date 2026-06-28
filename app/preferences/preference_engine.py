"""
Preference resolution: system default -> segment -> user -> regulatory mandate.

Each layer can narrow or reorder the channel list of the layer below it,
EXCEPT regulatory mandate, which can re-add a channel that a lower layer
removed (because SEBI-mandated content cannot be fully suppressed by user
preference — see compliance/sebi.py). This module is intentionally pure
(no DB session) so it's trivially unit-testable: feed it dataclasses, get
a decision back.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time

from app.domain.event_types import Channel, EventTypeSpec
from app.compliance.sebi import must_force_delivery, regulatory_minimum_channels


@dataclass
class ResolvedPreference:
    """What the router actually needs after walking the hierarchy."""
    channel_order: list[str]
    quiet_hours: tuple[time, time] | None
    max_promotional_per_day: int
    timezone: str = "Asia/Kolkata"


@dataclass
class UserPreferenceInput:
    """Mirror of the DB row, passed in as a plain object to keep this module DB-free."""
    preferred_channels: list[str] | None = None
    opted_out_channels: list[str] = field(default_factory=list)
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    timezone: str = "Asia/Kolkata"
    max_promotional_per_day: int = 3
    segment_default_channels: list[str] | None = None


def resolve_channel_order(spec: EventTypeSpec, pref: UserPreferenceInput) -> list[str]:
    # Layer 0: system default = the event type's own allowed_channels order
    order = [c.value for c in spec.allowed_channels]

    # Layer 1: segment default narrows/reorders, if present
    if pref.segment_default_channels:
        order = [c for c in pref.segment_default_channels if c in order] or order

    # Layer 2: user override replaces order entirely if user has expressed a preference
    if pref.preferred_channels:
        order = [c for c in pref.preferred_channels if c in order] or order

    # Apply opt-outs (user saying "never contact me on X")
    filtered = [c for c in order if c not in (pref.opted_out_channels or [])]

    # Layer 3: regulatory mandate — re-insert minimum-required channels even if
    # opted out, because a SEBI-mandated alert cannot be fully suppressed.
    if must_force_delivery(spec):
        mandatory = [c.value for c in regulatory_minimum_channels(spec)]
        for ch in mandatory:
            if ch not in filtered:
                filtered.append(ch)
        return filtered or mandatory

    return filtered


def _parse_time(value: str | None) -> time | None:
    if not value:
        return None
    hh, mm = value.split(":")
    return time(int(hh), int(mm))


def is_within_quiet_hours(pref: UserPreferenceInput, now: datetime) -> bool:
    start = _parse_time(pref.quiet_hours_start)
    end = _parse_time(pref.quiet_hours_end)
    if not start or not end:
        return False

    current = now.time()
    if start <= end:
        return start <= current <= end
    # overnight window, e.g. 22:00 -> 07:00
    return current >= start or current <= end


def resolve(spec: EventTypeSpec, pref: UserPreferenceInput) -> ResolvedPreference:
    return ResolvedPreference(
        channel_order=resolve_channel_order(spec, pref),
        quiet_hours=(_parse_time(pref.quiet_hours_start), _parse_time(pref.quiet_hours_end))
        if pref.quiet_hours_start else None,
        max_promotional_per_day=pref.max_promotional_per_day,
        timezone=pref.timezone,
    )
