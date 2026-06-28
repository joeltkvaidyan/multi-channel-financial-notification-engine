"""Append-only event store. Never UPDATE or DELETE a row here — that's the
whole point of event sourcing: the full history is the source of truth,
and current state (in the write model) is just a projection of it. If a
bug is ever found in the routing/compliance logic, every past event can
be replayed through the corrected logic to verify what *should* have
happened, which is invaluable for a regulated, audited system."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models import EventStoreEntry


def append_event(session: Session, event_code: str, user_id: str, payload: dict, correlation_id: str | None = None) -> EventStoreEntry:
    entry = EventStoreEntry(
        event_code=event_code,
        user_id=user_id,
        payload=payload,
        correlation_id=correlation_id or str(uuid.uuid4()),
    )
    session.add(entry)
    session.flush()   # need entry.id populated for the caller before commit
    return entry


def replay_for_user(session: Session, user_id: str) -> list[EventStoreEntry]:
    return (
        session.query(EventStoreEntry)
        .filter(EventStoreEntry.user_id == user_id)
        .order_by(EventStoreEntry.occurred_at.asc())
        .all()
    )
