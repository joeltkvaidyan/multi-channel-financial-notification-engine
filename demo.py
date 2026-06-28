"""
End-to-end demo: simulates a realistic stream of financial events through
the entire pipeline and prints what happened at each stage, so a reviewer
(or you, before a viva) can see every architectural pattern actually fire:

  Scenario 1 - MARGIN_CALL at 2 AM for a user with quiet hours 22:00-07:00
               -> regulatory mandate overrides quiet hours -> still delivered
  Scenario 2 - SIP_REMINDER for a user with no special preferences
               -> normal routing, engagement-based channel ordering
  Scenario 3 - MARKET_INSIGHTS_DIGEST (promotional) for a DND-registered user
               -> TRAI DND blocks it -> SUPPRESSED, audited
  Scenario 4 - ORDER_EXECUTED where every channel adapter is forced to fail
               -> saga retries each channel, exhausts the plan -> DEAD_LETTERED
  Scenario 5 - Bulk run across all 29 event types for one user -> shows the
               dashboard-ready analytics rollup forming in real time

Run: python -m demo   (from the project root, after `pip install -r requirements.txt`)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, time

from app.channels.registry import CHANNEL_REGISTRY
from app.cqrs.command_handlers import handle_event
from app.cqrs import query_handlers as q
from app.database import get_session, init_db
from app.domain.event_types import all_event_codes
from app.models import UserPreference


def _print_header(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


async def scenario_1_margin_call_overrides_quiet_hours():
    _print_header("SCENARIO 1: MARGIN_CALL at 2 AM overrides quiet hours (SEBI mandate)")
    with get_session() as session:
        pref = UserPreference(
            user_id="user_aarav", event_code=None,
            quiet_hours_start="22:00", quiet_hours_end="07:00",
            opted_out_channels=["PUSH"],   # even with push opted out...
        )
        session.add(pref)
        session.flush()

        notification = await handle_event(
            session=session,
            event_code="MARGIN_CALL",
            user_id="user_aarav",
            payload={
                "broker_name": "Zetheta Markets", "account_id": "ACC10293",
                "shortfall_amount": "42,500", "deadline": "2026-06-25 6:00 PM",
                "short_link": "zth.in/m/abc123",
                "full_link": "https://app.zetheta.com/margin/ACC10293",
                "customer_name": "Aarav",
            },
            pref_row=pref,
            dnd_registered=False,
            recipients={"SMS": "+919876543210", "EMAIL": "aarav@example.com", "PUSH": "device_token_xyz"},
        )

        print(f"-> state: {notification.state.value}")
        print(f"-> channel_plan (PUSH re-added despite opt-out, regulatory mandate): {notification.channel_plan}")
        print(f"-> suppression_reason: {notification.suppression_reason}")


async def scenario_2_sip_reminder_normal_routing():
    _print_header("SCENARIO 2: SIP_REMINDER with engagement-based channel ordering")
    with get_session() as session:
        pref = UserPreference(user_id="user_diya", event_code=None)
        session.add(pref)
        session.flush()

        notification = await handle_event(
            session=session,
            event_code="SIP_REMINDER",
            user_id="user_diya",
            payload={
                "broker_name": "Zetheta Markets", "sip_amount": "5,000",
                "fund_name": "Zetheta Flexicap Fund", "debit_date": "2026-06-28",
                "short_link": "zth.in/s/sip01", "customer_name": "Diya",
            },
            pref_row=pref,
            dnd_registered=False,
            recipients={"PUSH": "device_token_diya", "WHATSAPP": "+919812345678", "SMS": "+919812345678"},
            engagement_scores={"PUSH": 0.85, "WHATSAPP": 0.6, "SMS": 0.3},
        )
        print(f"-> state: {notification.state.value}")
        print(f"-> channel_plan (PUSH first - highest engagement): {notification.channel_plan}")


async def scenario_3_dnd_blocks_promotional():
    _print_header("SCENARIO 3: MARKET_INSIGHTS_DIGEST blocked by TRAI DND registration")
    with get_session() as session:
        pref = UserPreference(user_id="user_rohan", event_code=None, dnd_registered=True)
        session.add(pref)
        session.flush()

        notification = await handle_event(
            session=session,
            event_code="MARKET_INSIGHTS_DIGEST",
            user_id="user_rohan",
            payload={
                "broker_name": "Zetheta Markets",
                "headline_summary": "Nifty closed flat amid mixed global cues.",
                "top_movers": "TCS +2.1%, INFY -1.4%",
            },
            pref_row=pref,
            dnd_registered=True,
            recipients={"EMAIL": "rohan@example.com", "WHATSAPP": "+919800011122"},
        )
        print(f"-> state: {notification.state.value}")
        print(f"-> suppression_reason: {notification.suppression_reason}  (audited in event_store, never sent)")


async def scenario_4_all_channels_fail_to_dlq():
    _print_header("SCENARIO 4: ORDER_EXECUTED — forcing every channel to fail -> DLQ")
    # temporarily crank failure rates to 100% to deterministically prove the DLQ path
    original_rates = {name: ch.failure_rate for name, ch in CHANNEL_REGISTRY.items()}
    for ch in CHANNEL_REGISTRY.values():
        ch.failure_rate = 1.0

    try:
        with get_session() as session:
            pref = UserPreference(user_id="user_meera", event_code=None)
            session.add(pref)
            session.flush()

            notification = await handle_event(
                session=session,
                event_code="ORDER_EXECUTED",
                user_id="user_meera",
                payload={"side": "BUY", "qty": 50, "symbol": "RELIANCE", "price": "2,950"},
                pref_row=pref,
                dnd_registered=False,
                recipients={"PUSH": "device_token_meera", "SMS": "+919900011122", "EMAIL": "meera@example.com"},
            )
            print(f"-> state: {notification.state.value}  (every channel exhausted retries)")
            print(f"-> attempted plan: {notification.channel_plan}")

            dl_rows = q.recent_dead_letters(session, limit=5)
            print(f"-> dead_letters table now has {len(dl_rows)} row(s), most recent reason: {dl_rows[0]['reason'] if dl_rows else None}")
    finally:
        for name, ch in CHANNEL_REGISTRY.items():
            ch.failure_rate = original_rates[name]


async def scenario_5_bulk_run_for_dashboard():
    _print_header("SCENARIO 5: bulk run across all event types -> live analytics rollup")
    sample_payloads = {
        "default": {"broker_name": "Zetheta Markets", "customer_name": "Test User"},
    }
    with get_session() as session:
        pref = UserPreference(user_id="user_bulk", event_code=None)
        session.add(pref)
        session.flush()

        for code in all_event_codes():
            try:
                await handle_event(
                    session=session,
                    event_code=code,
                    user_id="user_bulk",
                    payload=sample_payloads["default"],
                    pref_row=pref,
                    dnd_registered=False,
                    recipients={
                        "SMS": "+919000000000", "EMAIL": "bulk@example.com",
                        "PUSH": "tok", "WHATSAPP": "+919000000000", "IN_APP": "user_bulk",
                    },
                )
            except Exception as exc:
                print(f"   ! {code} raised {exc!r}")

        print(f"-> processed {len(all_event_codes())} event types for user_bulk")
        print("-> /analytics/summary would now return:", q.delivery_summary(session))
        print("-> /analytics/by-channel:")
        for row in q.breakdown_by_channel(session):
            print("   ", row)


async def main():
    init_db()
    await scenario_1_margin_call_overrides_quiet_hours()
    await scenario_2_sip_reminder_normal_routing()
    await scenario_3_dnd_blocks_promotional()
    await scenario_4_all_channels_fail_to_dlq()
    await scenario_5_bulk_run_for_dashboard()
    print("\nDemo complete. Run `streamlit run dashboard.py` to view the analytics dashboard.\n")


if __name__ == "__main__":
    asyncio.run(main())
