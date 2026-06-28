"""Integration tests for the command-handler pipeline, against a throwaway
in-memory SQLite DB so tests are fully isolated and fast."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, LifecycleState, UserPreference
from app.cqrs.command_handlers import handle_event


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


def test_full_pipeline_delivers_sip_reminder(session):
    pref = UserPreference(user_id="itest_1", event_code=None)
    session.add(pref)
    session.flush()

    notification = asyncio.run(handle_event(
        session=session,
        event_code="SIP_REMINDER",
        user_id="itest_1",
        payload={"broker_name": "Z", "sip_amount": "1", "fund_name": "F", "debit_date": "2026-01-01", "short_link": "x", "customer_name": "C"},
        pref_row=pref,
        dnd_registered=False,
        recipients={"PUSH": "tok", "WHATSAPP": "+91", "SMS": "+91"},
    ))

    assert notification.state == LifecycleState.DELIVERED
    assert notification.event_store_id is not None


def test_full_pipeline_suppresses_dnd_promotional(session):
    pref = UserPreference(user_id="itest_2", event_code=None, dnd_registered=True)
    session.add(pref)
    session.flush()

    notification = asyncio.run(handle_event(
        session=session,
        event_code="MARKET_INSIGHTS_DIGEST",
        user_id="itest_2",
        payload={"broker_name": "Z", "headline_summary": "s", "top_movers": "m"},
        pref_row=pref,
        dnd_registered=True,
        recipients={"EMAIL": "x@y.com", "WHATSAPP": "+91"},
    ))

    assert notification.state == LifecycleState.SUPPRESSED
    assert notification.suppression_reason == "TRAI_DND_REGISTERED_PROMOTIONAL_BLOCKED"
