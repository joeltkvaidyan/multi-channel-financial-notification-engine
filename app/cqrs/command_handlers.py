"""
CQRS — Command side.

This is the write path: ingest a raw event, run it through compliance +
routing, render templates, persist a `Notification`, and hand off to the
Saga for delivery. Optimised for throughput and correctness, not for
flexible querying — that's deliberately the read side's job
(`query_handlers.py`), which is why this module never does an aggregate
query or a dashboard-shaped read.

In a real deployment, this function is what a Kafka consumer (consumer
group: "notification-ingestion") calls for every message on the
"raw.events" topic. Multiple instances of this consumer group can run in
parallel, partitioned by user_id, which is exactly why `user_id` is the
event's Kafka partition key in event_bus.py's design notes.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.domain.event_types import get_spec
from app.event_sourcing.event_store import append_event
from app.models import LifecycleState, Notification
from app.preferences.frequency_cap import record_send
from app.preferences.preference_engine import UserPreferenceInput
from app.routing.router import route
from app.saga.notification_saga import run_saga
from app.templates_engine.renderer import render
from app.dlq.dead_letter_queue import dead_letter
from app.analytics.lifecycle_tracker import record_transition

logger = logging.getLogger("notification_engine.cqrs.command")


def _build_pref_input(pref_row) -> UserPreferenceInput:
    if pref_row is None:
        return UserPreferenceInput()
    return UserPreferenceInput(
        preferred_channels=pref_row.preferred_channels,
        opted_out_channels=pref_row.opted_out_channels or [],
        quiet_hours_start=pref_row.quiet_hours_start,
        quiet_hours_end=pref_row.quiet_hours_end,
        timezone=pref_row.timezone,
        max_promotional_per_day=pref_row.max_promotional_per_day,
    )


async def handle_event(
    session: Session,
    event_code: str,
    user_id: str,
    payload: dict,
    pref_row,
    dnd_registered: bool,
    recipients: dict[str, str],
    engagement_scores: dict[str, float] | None = None,
    locale: str = "en",
) -> Notification:
    """The full command pipeline for one event. Returns the persisted Notification."""

    spec = get_spec(event_code)

    # 1. Event sourcing: durably record the raw event first, no matter what
    #    happens downstream. This guarantees nothing is ever lost even if
    #    routing/rendering throws.
    event_entry = append_event(session, event_code, user_id, payload)

    # 2. Routing decision (compliance + preferences + engagement + cost)
    pref_input = _build_pref_input(pref_row)
    decision = route(
        event_code=event_code,
        pref=pref_input,
        dnd_registered=dnd_registered,
        engagement_scores=engagement_scores,
        user_id=user_id,
        now=datetime.now(),
    )

    notification = Notification(
        event_store_id=event_entry.id,
        user_id=user_id,
        event_code=event_code,
        classification=spec.classification.value,
        priority=spec.priority.value,
        channel_plan=decision.channel_plan,
        state=LifecycleState.CREATED,
    )
    session.add(notification)
    session.flush()
    record_transition(session, notification, LifecycleState.CREATED)

    if not decision.allowed:
        notification.state = LifecycleState.SUPPRESSED
        notification.suppression_reason = decision.suppression_reason
        session.add(notification)
        record_transition(session, notification, LifecycleState.SUPPRESSED)
        logger.info("notification suppressed: user=%s event=%s reason=%s", user_id, event_code, decision.suppression_reason)
        return notification

    # 3. Render templates per channel in the plan
    rendered = {
        ch: render(ch, event_code, payload, locale=locale)
        for ch in decision.channel_plan
    }
    notification.rendered_content = rendered
    notification.state = LifecycleState.ROUTED
    session.add(notification)
    record_transition(session, notification, LifecycleState.ROUTED)

    # 4. Hand off to the Saga for multi-channel delivery with retry/fallback
    notification.state = LifecycleState.QUEUED
    session.add(notification)
    record_transition(session, notification, LifecycleState.QUEUED)

    saga_result = await run_saga(decision.channel_plan, recipients, rendered)

    if saga_result.delivered:
        notification.state = LifecycleState.DELIVERED
        session.add(notification)
        record_transition(session, notification, LifecycleState.DELIVERED, channel=saga_result.delivered_channel)
        record_send(spec, user_id)   # only counts toward frequency cap on actual send
    else:
        notification.state = LifecycleState.FAILED
        session.add(notification)
        record_transition(session, notification, LifecycleState.FAILED)
        dead_letter(session, notification, reason="ALL_CHANNELS_EXHAUSTED", last_payload=payload)
        record_transition(session, notification, LifecycleState.DEAD_LETTERED)

    return notification
