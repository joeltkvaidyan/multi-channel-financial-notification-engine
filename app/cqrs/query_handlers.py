"""
CQRS — Query side.

Reads exclusively from the denormalized `NotificationMetricsDaily` table
(and, for drill-downs, the lighter-weight `Notification`/`DeadLetter`
tables) — never from `EventStoreEntry`, which would require scanning the
entire audit log to compute a dashboard number. This is the entire point
of separating command and query responsibilities: the dashboard can be
queried as often and by as many analysts as needed without putting any
load on the ingestion path.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import DeadLetter, LifecycleState, Notification, NotificationMetricsDaily


def delivery_summary(session: Session, metric_date: str | None = None) -> dict:
    query = session.query(
        func.sum(NotificationMetricsDaily.created_count),
        func.sum(NotificationMetricsDaily.sent_count),
        func.sum(NotificationMetricsDaily.delivered_count),
        func.sum(NotificationMetricsDaily.failed_count),
        func.sum(NotificationMetricsDaily.suppressed_count),
        func.sum(NotificationMetricsDaily.dead_lettered_count),
    )
    if metric_date:
        query = query.filter(NotificationMetricsDaily.metric_date == metric_date)

    created, sent, delivered, failed, suppressed, dead_lettered = query.one()
    return {
        "created": created or 0,
        "sent": sent or 0,
        "delivered": delivered or 0,
        "failed": failed or 0,
        "suppressed": suppressed or 0,
        "dead_lettered": dead_lettered or 0,
    }


def breakdown_by_channel(session: Session, metric_date: str | None = None) -> list[dict]:
    query = session.query(
        NotificationMetricsDaily.channel,
        func.sum(NotificationMetricsDaily.created_count),
        func.sum(NotificationMetricsDaily.delivered_count),
        func.sum(NotificationMetricsDaily.failed_count),
    )
    if metric_date:
        query = query.filter(NotificationMetricsDaily.metric_date == metric_date)
    query = query.group_by(NotificationMetricsDaily.channel)

    return [
        {"channel": ch, "created": c or 0, "delivered": d or 0, "failed": f or 0}
        for ch, c, d, f in query.all()
    ]


def breakdown_by_event_type(session: Session, metric_date: str | None = None) -> list[dict]:
    query = session.query(
        NotificationMetricsDaily.event_code,
        func.sum(NotificationMetricsDaily.created_count),
        func.sum(NotificationMetricsDaily.delivered_count),
        func.sum(NotificationMetricsDaily.suppressed_count),
    )
    if metric_date:
        query = query.filter(NotificationMetricsDaily.metric_date == metric_date)
    query = query.group_by(NotificationMetricsDaily.event_code)

    return [
        {"event_code": ec, "created": c or 0, "delivered": d or 0, "suppressed": s or 0}
        for ec, c, d, s in query.all()
    ]


def recent_dead_letters(session: Session, limit: int = 20) -> list[dict]:
    rows = (
        session.query(DeadLetter, Notification)
        .join(Notification, DeadLetter.notification_id == Notification.id)
        .order_by(DeadLetter.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "dead_letter_id": dl.id,
            "notification_id": n.id,
            "user_id": n.user_id,
            "event_code": n.event_code,
            "reason": dl.reason,
            "requeued": dl.requeued,
            "created_at": dl.created_at.isoformat() if dl.created_at else None,
        }
        for dl, n in rows
    ]


def notifications_for_user(session: Session, user_id: str, limit: int = 50) -> list[dict]:
    rows = (
        session.query(Notification)
        .filter(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": n.id,
            "event_code": n.event_code,
            "state": n.state.value if isinstance(n.state, LifecycleState) else n.state,
            "channel_plan": n.channel_plan,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in rows
    ]
