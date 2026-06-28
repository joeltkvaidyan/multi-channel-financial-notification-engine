"""
Channel Routing Engine.

Decision order, exactly as specified in the brief, highest authority first:

  1. Regulatory mandate (non-negotiable)       -> compliance/sebi.py
  2. TRAI DND / promotional window              -> compliance/trai_dnd.py
  3. User preference (hierarchical)             -> preferences/preference_engine.py
  4. Frequency cap / quiet hours                -> preferences/frequency_cap.py,
                                                    preferences/preference_engine.py
  5. Delivery optimisation (engagement history) -> reorder by historical
     open/delivery rate per channel for this user
  6. Cost optimisation (business rule)          -> among equally-engaging
     channels, prefer the cheaper one (push/in-app free, SMS/WhatsApp cost
     per message, email near-free)

The output is a `RoutingDecision`: either an ordered channel_plan the Saga
should attempt in sequence, or a suppression with a reason (for audit).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.event_types import Channel, EventTypeSpec, get_spec
from app.compliance.trai_dnd import check_trai_compliance
from app.compliance.sebi import must_force_delivery
from app.preferences.preference_engine import (
    UserPreferenceInput, resolve_channel_order, is_within_quiet_hours,
)
from app.preferences.frequency_cap import exceeds_cap

# Relative cost per send, arbitrary units — used only to break ties between
# channels with similar engagement when no regulatory/user constraint applies.
CHANNEL_COST = {
    Channel.IN_APP.value: 0,
    Channel.PUSH.value: 1,
    Channel.EMAIL.value: 2,
    Channel.WHATSAPP.value: 6,
    Channel.SMS.value: 8,
}


@dataclass
class RoutingDecision:
    allowed: bool
    channel_plan: list[str]
    suppression_reason: str | None = None


def _reorder_by_engagement(channels: list[str], engagement_scores: dict[str, float] | None) -> list[str]:
    """engagement_scores: e.g. {"PUSH": 0.92, "SMS": 0.4} = historical open/delivery
    rate for this user on this channel. Higher = more likely to actually be seen.
    Falls back to cost-based tiebreak when no engagement data exists."""
    if not engagement_scores:
        return sorted(channels, key=lambda c: CHANNEL_COST.get(c, 99))

    def score(c: str) -> tuple:
        # primary: engagement (desc); tiebreak: cost (asc)
        return (-engagement_scores.get(c, 0.0), CHANNEL_COST.get(c, 99))

    return sorted(channels, key=score)


def route(
    event_code: str,
    pref: UserPreferenceInput,
    dnd_registered: bool,
    today_promotional_count_check: bool = True,
    engagement_scores: dict[str, float] | None = None,
    now: datetime | None = None,
    user_id: str = "",
) -> RoutingDecision:
    now = now or datetime.now()
    spec: EventTypeSpec = get_spec(event_code)

    # 1 & 2: regulatory + TRAI compliance gate
    forced = must_force_delivery(spec)
    allowed, reason = check_trai_compliance(spec, dnd_registered, now)
    if not allowed and not forced:
        return RoutingDecision(allowed=False, channel_plan=[], suppression_reason=reason)

    # 3: hierarchical preference resolution (already folds in regulatory re-add)
    channels = resolve_channel_order(spec, pref)
    if not channels:
        return RoutingDecision(allowed=False, channel_plan=[], suppression_reason="NO_VIABLE_CHANNEL")

    # 4a: frequency cap (promotional only; never blocks regulatory-mandatory)
    if today_promotional_count_check and not forced:
        if exceeds_cap(spec, user_id, pref.max_promotional_per_day):
            return RoutingDecision(allowed=False, channel_plan=[], suppression_reason="FREQUENCY_CAP_EXCEEDED")

    # 4b: quiet hours (never blocks CRITICAL/regulatory-mandatory alerts —
    # a margin call at 2am still needs to reach the user)
    if is_within_quiet_hours(pref, now) and not forced:
        return RoutingDecision(allowed=False, channel_plan=[], suppression_reason="WITHIN_QUIET_HOURS")

    # 5 & 6: engagement-based reorder with cost as tiebreak
    ordered = _reorder_by_engagement(channels, engagement_scores)

    return RoutingDecision(allowed=True, channel_plan=ordered, suppression_reason=None)
