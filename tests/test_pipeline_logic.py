"""
Unit tests for the pure-logic modules: compliance, preference resolution,
routing, and frequency capping. These don't touch the DB or network, so
they run in milliseconds and are the tests a reviewer would run first.

Run: pytest tests/ -v
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.domain.event_types import get_spec
from app.compliance.trai_dnd import check_trai_compliance
from app.compliance.sebi import must_force_delivery
from app.preferences.preference_engine import (
    UserPreferenceInput, is_within_quiet_hours, resolve_channel_order,
)
from app.preferences.frequency_cap import exceeds_cap, record_send, get_tracker
from app.routing.router import route


# ---------------------------------------------------------------------------
# Compliance
# ---------------------------------------------------------------------------
def test_transactional_never_blocked_by_dnd():
    spec = get_spec("MARGIN_CALL")
    allowed, reason = check_trai_compliance(spec, dnd_registered=True)
    assert allowed is True
    assert reason is None


def test_promotional_blocked_for_dnd_registered_user():
    spec = get_spec("MARKET_INSIGHTS_DIGEST")
    allowed, reason = check_trai_compliance(spec, dnd_registered=True)
    assert allowed is False
    assert reason == "TRAI_DND_REGISTERED_PROMOTIONAL_BLOCKED"


def test_promotional_outside_window_blocked_even_without_dnd():
    spec = get_spec("MARKET_INSIGHTS_DIGEST")
    late_night = datetime(2026, 6, 28, 23, 30)
    allowed, reason = check_trai_compliance(spec, dnd_registered=False, now=late_night)
    assert allowed is False
    assert reason == "OUTSIDE_TRAI_PROMOTIONAL_WINDOW"


def test_margin_call_is_regulatory_mandatory():
    assert must_force_delivery(get_spec("MARGIN_CALL")) is True


def test_sip_reminder_is_not_regulatory_mandatory():
    assert must_force_delivery(get_spec("SIP_REMINDER")) is False


# ---------------------------------------------------------------------------
# Preference hierarchy
# ---------------------------------------------------------------------------
def test_user_opt_out_removes_channel_for_non_mandatory_event():
    spec = get_spec("SIP_REMINDER")
    pref = UserPreferenceInput(opted_out_channels=["PUSH"])
    order = resolve_channel_order(spec, pref)
    assert "PUSH" not in order


def test_regulatory_mandate_reinstates_opted_out_channel():
    spec = get_spec("MARGIN_CALL")
    pref = UserPreferenceInput(opted_out_channels=["SMS"])
    order = resolve_channel_order(spec, pref)
    assert "SMS" in order   # SEBI mandate overrides the user opt-out


def test_user_preferred_channels_reorder_default():
    spec = get_spec("SIP_REMINDER")  # default order: PUSH, WHATSAPP, SMS
    pref = UserPreferenceInput(preferred_channels=["SMS", "PUSH"])
    order = resolve_channel_order(spec, pref)
    assert order[0] == "SMS"


def test_quiet_hours_overnight_window():
    pref = UserPreferenceInput(quiet_hours_start="22:00", quiet_hours_end="07:00")
    assert is_within_quiet_hours(pref, datetime(2026, 6, 28, 2, 0)) is True
    assert is_within_quiet_hours(pref, datetime(2026, 6, 28, 12, 0)) is False


# ---------------------------------------------------------------------------
# Frequency capping
# ---------------------------------------------------------------------------
def test_frequency_cap_blocks_promotional_after_limit():
    spec = get_spec("MARKET_INSIGHTS_DIGEST")
    user_id = "test_freq_cap_user"
    today = date(2026, 6, 28)
    for _ in range(3):
        record_send(spec, user_id, today)
    assert exceeds_cap(spec, user_id, max_per_day=3, today=today) is True


def test_frequency_cap_never_applies_to_transactional():
    spec = get_spec("MARGIN_CALL")
    assert exceeds_cap(spec, "any_user", max_per_day=0) is False


# ---------------------------------------------------------------------------
# Router: end-to-end decision composition
# ---------------------------------------------------------------------------
def test_router_suppresses_dnd_promotional():
    pref = UserPreferenceInput()
    decision = route(
        "MARKET_INSIGHTS_DIGEST", pref, dnd_registered=True,
        now=datetime(2026, 6, 28, 14, 0), user_id="ru1",
    )
    assert decision.allowed is False
    assert decision.suppression_reason == "TRAI_DND_REGISTERED_PROMOTIONAL_BLOCKED"


def test_router_forces_margin_call_through_quiet_hours():
    pref = UserPreferenceInput(quiet_hours_start="22:00", quiet_hours_end="07:00")
    decision = route(
        "MARGIN_CALL", pref, dnd_registered=False,
        now=datetime(2026, 6, 28, 3, 0), user_id="ru2",
    )
    assert decision.allowed is True
    assert len(decision.channel_plan) > 0


def test_router_blocks_normal_event_during_quiet_hours():
    pref = UserPreferenceInput(quiet_hours_start="22:00", quiet_hours_end="07:00")
    decision = route(
        "SIP_REMINDER", pref, dnd_registered=False,
        now=datetime(2026, 6, 28, 3, 0), user_id="ru3",
    )
    assert decision.allowed is False
    assert decision.suppression_reason == "WITHIN_QUIET_HOURS"


def test_router_orders_by_engagement_then_cost():
    pref = UserPreferenceInput()
    decision = route(
        "SIP_REMINDER", pref, dnd_registered=False,
        engagement_scores={"PUSH": 0.2, "SMS": 0.9, "WHATSAPP": 0.9},
        now=datetime(2026, 6, 28, 14, 0), user_id="ru4",
    )
    # SMS and WHATSAPP tie on engagement (0.9); WHATSAPP is cheaper -> comes first
    assert decision.channel_plan[0] in ("WHATSAPP", "SMS")
    assert decision.channel_plan[0] != "PUSH"
