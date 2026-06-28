"""
Lifecycle tracker: records every state transition a notification goes
through (CREATED -> ... -> DELIVERED/FAILED) and rolls it into the
denormalized daily metrics table that the analytics dashboard reads from.

This is the bridge between the write model and the read model in CQRS. In
a real Kafka deployment, this would NOT be called inline from the command
handler (that would couple write and read paths again, defeating the
purpose of CQRS) — it would be a separate consumer reading the
"analytics.lifecycle" topic. It's called inline here only because the
demo runs as a single process with no broker; the seam is intentionally
kept as a single function call so swapping it for an async consumer later
is a non-event.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.models import LifecycleState, Notification, NotificationMetricsDaily


def _get_or_create_metric_row(session: Session, metric_date: str, event_code: str, channel: str) -> NotificationMetricsDaily:
    row = (
        session.query(NotificationMetricsDaily)
        .filter_by(metric_date=metric_date, event_code=event_code, channel=channel)
        .one_or_none()
    )
    if row is None:
        row = NotificationMetricsDaily(metric_date=metric_date, event_code=event_code, channel=channel)
        session.add(row)
        session.flush()
    return row


_STATE_TO_COLUMN = {
    LifecycleState.CREATED: "created_count",
    LifecycleState.SENT: "sent_count",
    LifecycleState.DELIVERED: "delivered_count",
    LifecycleState.READ: "read_count",
    LifecycleState.FAILED: "failed_count",
    LifecycleState.SUPPRESSED: "suppressed_count",
    LifecycleState.DEAD_LETTERED: "dead_lettered_count",
}


def record_transition(session: Session, notification: Notification, state: LifecycleState, channel: str | None = None) -> None:
    if state not in _STATE_TO_COLUMN:
        return   # QUEUED/ROUTED are intermediate, not rolled up into the dashboard metrics

    today = date.today().isoformat()
    # When no specific channel succeeded yet, attribute to the first planned
    # channel so CREATED/SUPPRESSED rows still show up under some channel.
    channel = channel or (notification.channel_plan[0] if notification.channel_plan else "NONE")

    row = _get_or_create_metric_row(session, today, notification.event_code, channel)
    column = _STATE_TO_COLUMN[state]
    setattr(row, column, getattr(row, column) + 1)
    session.add(row)
    session.flush()
