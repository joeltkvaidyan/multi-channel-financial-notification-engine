"""
FastAPI surface.

Three endpoint groups, mirroring the CQRS split:
  - POST /events/ingest               -> command side (triggers the full pipeline)
  - GET  /users/{id}/notifications    -> per-user lookup (lightweight read)
  - PUT  /users/{id}/preferences      -> preference management
  - GET  /analytics/*                 -> query side (dashboard data source)
  - GET  /dlq                         -> ops visibility into dead letters
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.cqrs.command_handlers import handle_event
from app.cqrs import query_handlers as q
from app.database import get_session, init_db
from app.domain.event_types import all_event_codes
from app.models import UserPreference

app = FastAPI(
    title="DocuMind-Adjacent Notification Engine",
    description="Multi-channel financial notification engine — Zetheta internship project",
    version="1.0.0",
)


@app.on_event("startup")
def _startup() -> None:
    init_db()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class IngestEventRequest(BaseModel):
    event_code: str
    user_id: str
    payload: dict
    recipients: dict[str, str]   # {"SMS": "+91...", "EMAIL": "x@y.com", ...}
    engagement_scores: Optional[dict[str, float]] = None
    locale: str = "en"


class PreferenceUpdateRequest(BaseModel):
    preferred_channels: Optional[list[str]] = None
    opted_out_channels: Optional[list[str]] = None
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None
    timezone: Optional[str] = None
    dnd_registered: Optional[bool] = None
    max_promotional_per_day: Optional[int] = None


# ---------------------------------------------------------------------------
# Command side
# ---------------------------------------------------------------------------
@app.post("/events/ingest")
async def ingest_event(req: IngestEventRequest):
    if req.event_code not in all_event_codes():
        raise HTTPException(400, f"Unknown event_code. Valid codes: {all_event_codes()}")

    with get_session() as session:
        pref_row = (
            session.query(UserPreference)
            .filter(UserPreference.user_id == req.user_id, UserPreference.event_code.is_(None))
            .one_or_none()
        )
        dnd = bool(pref_row.dnd_registered) if pref_row else False

        notification = await handle_event(
            session=session,
            event_code=req.event_code,
            user_id=req.user_id,
            payload=req.payload,
            pref_row=pref_row,
            dnd_registered=dnd,
            recipients=req.recipients,
            engagement_scores=req.engagement_scores,
            locale=req.locale,
        )
        return {
            "notification_id": notification.id,
            "state": notification.state.value,
            "channel_plan": notification.channel_plan,
            "suppression_reason": notification.suppression_reason,
        }


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------
@app.put("/users/{user_id}/preferences")
def update_preferences(user_id: str, req: PreferenceUpdateRequest):
    with get_session() as session:
        row = (
            session.query(UserPreference)
            .filter(UserPreference.user_id == user_id, UserPreference.event_code.is_(None))
            .one_or_none()
        )
        if row is None:
            row = UserPreference(user_id=user_id, event_code=None)

        for field, value in req.model_dump(exclude_unset=True).items():
            setattr(row, field, value)

        session.add(row)
        session.flush()
        return {"user_id": user_id, "updated": True}


@app.get("/users/{user_id}/notifications")
def get_user_notifications(user_id: str, limit: int = 50):
    with get_session() as session:
        return q.notifications_for_user(session, user_id, limit)


# ---------------------------------------------------------------------------
# Query side (analytics)
# ---------------------------------------------------------------------------
@app.get("/analytics/summary")
def analytics_summary(metric_date: Optional[str] = None):
    with get_session() as session:
        return q.delivery_summary(session, metric_date)


@app.get("/analytics/by-channel")
def analytics_by_channel(metric_date: Optional[str] = None):
    with get_session() as session:
        return q.breakdown_by_channel(session, metric_date)


@app.get("/analytics/by-event-type")
def analytics_by_event_type(metric_date: Optional[str] = None):
    with get_session() as session:
        return q.breakdown_by_event_type(session, metric_date)


@app.get("/dlq")
def dead_letters(limit: int = 20):
    with get_session() as session:
        return q.recent_dead_letters(session, limit)


@app.get("/event-catalog")
def event_catalog():
    return {"event_codes": all_event_codes()}


@app.get("/health")
def health():
    return {"status": "ok", "today": date.today().isoformat()}
