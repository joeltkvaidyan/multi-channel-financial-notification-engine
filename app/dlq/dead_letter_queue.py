"""
Dead Letter Queue handling.

A notification lands here only after the Saga has exhausted every channel
in its plan with full retries — i.e. every contact method on file for this
user has failed. This is rare but must never be silently dropped:

  - it's persisted (DeadLetter row) so support/compliance can see exactly
    which users did NOT receive a regulatory-mandatory alert and act
    (e.g. manual outreach, phone call) — this matters most for things like
    margin calls where "the message never arrived" is not an acceptable
    end state.
  - it can be requeued (manually or by a scheduled sweep) once, say, a
    user's phone number is corrected, or a provider outage recovers.

In a real Kafka deployment this would be the consumer's "max retries
exceeded" path publishing to a `notifications.dlq` topic, with a
separate, low-volume consumer group responsible for alerting on-call and
supporting manual requeue.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import DeadLetter, LifecycleState, Notification

logger = logging.getLogger("notification_engine.dlq")


def dead_letter(session: Session, notification: Notification, reason: str, last_payload: dict | None = None) -> DeadLetter:
    entry = DeadLetter(
        notification_id=notification.id,
        reason=reason,
        last_payload=last_payload or {},
    )
    notification.state = LifecycleState.DEAD_LETTERED
    session.add(entry)
    session.add(notification)
    session.flush()
    logger.error("notification %s dead-lettered: %s", notification.id, reason)
    return entry


def requeue(session: Session, dead_letter_id: str) -> DeadLetter | None:
    """Manual/scheduled requeue path: a human (or an automated sweep that
    detects, e.g., a corrected phone number) can re-attempt delivery."""
    entry = session.get(DeadLetter, dead_letter_id)
    if not entry:
        return None
    entry.requeued = True
    entry.requeued_at = datetime.now(timezone.utc)
    session.add(entry)
    return entry
