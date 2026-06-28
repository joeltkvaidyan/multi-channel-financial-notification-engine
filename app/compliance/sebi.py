"""
SEBI regulatory mandates.

A subset of notification types are not optional from a regulatory
standpoint — SEBI (and exchange bye-laws) require brokers to inform
clients of certain events regardless of marketing preferences:
margin calls, contract notes, KYC suspensions, risk limit breaches, etc.
(`EventTypeSpec.regulatory_mandatory`).

The rule encoded here is simple but important: regulatory mandates sit
ABOVE user preference in the override hierarchy. A user can opt out of
push notifications entirely, but if an event is `regulatory_mandatory`,
the router must still guarantee delivery on at least one channel the user
has not also blocked entirely (you can't physically force-deliver to a
channel the user has no presence on, e.g. no phone number on file).
"""

from __future__ import annotations

from app.domain.event_types import EventTypeSpec


def must_force_delivery(spec: EventTypeSpec) -> bool:
    return spec.regulatory_mandatory


def regulatory_minimum_channels(spec: EventTypeSpec) -> tuple:
    """The channel set that regulatory mandate requires consideration of,
    in priority order. The router will still skip channels the user has no
    contact info for, but will NOT skip them purely due to opt-out
    preference when this mandate is active."""
    return spec.allowed_channels
