"""
Domain catalog of financial notification event types.

Every event type carries the metadata the rest of the pipeline depends on:
  - classification: TRANSACTIONAL vs PROMOTIONAL (drives DND scrubbing)
  - regulatory_mandatory: if True, the notification MUST be attempted on at
    least one channel regardless of user opt-outs or quiet hours (SEBI rule)
  - default_priority: used by the router for channel selection & retries
  - allowed_channels: channels this event type is permitted on at all
    (e.g. margin calls should never be PUSH-only; SMS/Email/WhatsApp must
    be in the mix because push notifications can be missed/disabled)

This table is the single source of truth referenced by the compliance
layer, the router, and the template engine. Adding a new event type means
adding one row here.
"""

from dataclasses import dataclass
from enum import Enum


class Classification(str, Enum):
    TRANSACTIONAL = "TRANSACTIONAL"   # SEBI/regulatory, DND does not apply
    PROMOTIONAL = "PROMOTIONAL"       # marketing, subject to TRAI DND + opt-out


class Priority(str, Enum):
    CRITICAL = "CRITICAL"   # margin calls, KYC suspension - bypass quiet hours
    HIGH = "HIGH"            # order fills, payment failures
    MEDIUM = "MEDIUM"        # price alerts, SIP reminders
    LOW = "LOW"              # newsletters, promotions


class Channel(str, Enum):
    SMS = "SMS"
    EMAIL = "EMAIL"
    PUSH = "PUSH"
    WHATSAPP = "WHATSAPP"
    IN_APP = "IN_APP"


@dataclass(frozen=True)
class EventTypeSpec:
    code: str
    label: str
    classification: Classification
    priority: Priority
    regulatory_mandatory: bool
    allowed_channels: tuple  # ordered preference, router picks first viable


# ---------------------------------------------------------------------------
# 25+ financial event types covering trading, payments, compliance, and
# lifecycle/marketing communication for a brokerage / wealth platform.
# ---------------------------------------------------------------------------
EVENT_CATALOG: dict[str, EventTypeSpec] = {

    # --- Risk & margin (CRITICAL, regulatory) ---------------------------------
    "MARGIN_CALL": EventTypeSpec(
        "MARGIN_CALL", "Margin Call Issued", Classification.TRANSACTIONAL,
        Priority.CRITICAL, True,
        (Channel.SMS, Channel.PUSH, Channel.EMAIL, Channel.WHATSAPP)),
    "MARGIN_SHORTFALL_AUTO_LIQUIDATION": EventTypeSpec(
        "MARGIN_SHORTFALL_AUTO_LIQUIDATION", "Auto Square-off Triggered",
        Classification.TRANSACTIONAL, Priority.CRITICAL, True,
        (Channel.SMS, Channel.PUSH, Channel.EMAIL)),
    "RISK_LIMIT_BREACH": EventTypeSpec(
        "RISK_LIMIT_BREACH", "Risk Limit Breached", Classification.TRANSACTIONAL,
        Priority.CRITICAL, True, (Channel.SMS, Channel.PUSH, Channel.EMAIL)),

    # --- Orders & trades (HIGH, regulatory contract notes) --------------------
    "ORDER_PLACED": EventTypeSpec(
        "ORDER_PLACED", "Order Placed", Classification.TRANSACTIONAL,
        Priority.HIGH, False, (Channel.PUSH, Channel.IN_APP, Channel.SMS)),
    "ORDER_EXECUTED": EventTypeSpec(
        "ORDER_EXECUTED", "Order Executed", Classification.TRANSACTIONAL,
        Priority.HIGH, True, (Channel.PUSH, Channel.SMS, Channel.EMAIL)),
    "ORDER_REJECTED": EventTypeSpec(
        "ORDER_REJECTED", "Order Rejected", Classification.TRANSACTIONAL,
        Priority.HIGH, True, (Channel.PUSH, Channel.SMS, Channel.EMAIL)),
    "ORDER_PARTIALLY_FILLED": EventTypeSpec(
        "ORDER_PARTIALLY_FILLED", "Order Partially Filled",
        Classification.TRANSACTIONAL, Priority.MEDIUM, False,
        (Channel.PUSH, Channel.IN_APP)),
    "TRADE_CONTRACT_NOTE": EventTypeSpec(
        "TRADE_CONTRACT_NOTE", "Contract Note Generated",
        Classification.TRANSACTIONAL, Priority.HIGH, True,
        (Channel.EMAIL, Channel.IN_APP)),

    # --- Payments & funds (HIGH, regulatory) -----------------------------------
    "FUNDS_ADDED": EventTypeSpec(
        "FUNDS_ADDED", "Funds Added", Classification.TRANSACTIONAL,
        Priority.HIGH, True, (Channel.SMS, Channel.PUSH, Channel.EMAIL)),
    "FUNDS_WITHDRAWN": EventTypeSpec(
        "FUNDS_WITHDRAWN", "Withdrawal Processed", Classification.TRANSACTIONAL,
        Priority.HIGH, True, (Channel.SMS, Channel.PUSH, Channel.EMAIL)),
    "PAYMENT_FAILED": EventTypeSpec(
        "PAYMENT_FAILED", "Payment Failed", Classification.TRANSACTIONAL,
        Priority.HIGH, True, (Channel.SMS, Channel.PUSH, Channel.EMAIL)),
    "SIP_DEBIT_SUCCESS": EventTypeSpec(
        "SIP_DEBIT_SUCCESS", "SIP Installment Successful",
        Classification.TRANSACTIONAL, Priority.MEDIUM, False,
        (Channel.PUSH, Channel.IN_APP, Channel.EMAIL)),
    "SIP_DEBIT_FAILED": EventTypeSpec(
        "SIP_DEBIT_FAILED", "SIP Installment Failed",
        Classification.TRANSACTIONAL, Priority.HIGH, True,
        (Channel.SMS, Channel.PUSH, Channel.EMAIL)),
    "SIP_REMINDER": EventTypeSpec(
        "SIP_REMINDER", "Upcoming SIP Reminder", Classification.TRANSACTIONAL,
        Priority.MEDIUM, False, (Channel.PUSH, Channel.WHATSAPP, Channel.SMS)),

    # --- Market & price alerts (MEDIUM, user-configured) -----------------------
    "PRICE_ALERT_TRIGGERED": EventTypeSpec(
        "PRICE_ALERT_TRIGGERED", "Price Alert Triggered",
        Classification.TRANSACTIONAL, Priority.MEDIUM, False,
        (Channel.PUSH, Channel.SMS)),
    "STOP_LOSS_TRIGGERED": EventTypeSpec(
        "STOP_LOSS_TRIGGERED", "Stop-Loss Triggered", Classification.TRANSACTIONAL,
        Priority.HIGH, True, (Channel.PUSH, Channel.SMS, Channel.EMAIL)),
    "CORPORATE_ACTION_DIVIDEND": EventTypeSpec(
        "CORPORATE_ACTION_DIVIDEND", "Dividend Credited",
        Classification.TRANSACTIONAL, Priority.MEDIUM, False,
        (Channel.EMAIL, Channel.IN_APP, Channel.PUSH)),
    "CORPORATE_ACTION_SPLIT_BONUS": EventTypeSpec(
        "CORPORATE_ACTION_SPLIT_BONUS", "Stock Split / Bonus Processed",
        Classification.TRANSACTIONAL, Priority.MEDIUM, False,
        (Channel.EMAIL, Channel.IN_APP)),
    "IPO_ALLOTMENT_STATUS": EventTypeSpec(
        "IPO_ALLOTMENT_STATUS", "IPO Allotment Status", Classification.TRANSACTIONAL,
        Priority.HIGH, False, (Channel.PUSH, Channel.SMS, Channel.EMAIL)),

    # --- Compliance / KYC / account (CRITICAL-HIGH, regulatory) ----------------
    "KYC_DOCUMENT_EXPIRING": EventTypeSpec(
        "KYC_DOCUMENT_EXPIRING", "KYC Document Expiring Soon",
        Classification.TRANSACTIONAL, Priority.HIGH, True,
        (Channel.EMAIL, Channel.SMS, Channel.PUSH)),
    "KYC_SUSPENDED": EventTypeSpec(
        "KYC_SUSPENDED", "Account Suspended - KYC Non-Compliance",
        Classification.TRANSACTIONAL, Priority.CRITICAL, True,
        (Channel.SMS, Channel.EMAIL, Channel.PUSH)),
    "LOGIN_NEW_DEVICE": EventTypeSpec(
        "LOGIN_NEW_DEVICE", "New Device Login Detected",
        Classification.TRANSACTIONAL, Priority.HIGH, True,
        (Channel.SMS, Channel.EMAIL, Channel.PUSH)),
    "PASSWORD_CHANGED": EventTypeSpec(
        "PASSWORD_CHANGED", "Password Changed", Classification.TRANSACTIONAL,
        Priority.HIGH, True, (Channel.SMS, Channel.EMAIL)),
    "ANNUAL_TAX_STATEMENT_READY": EventTypeSpec(
        "ANNUAL_TAX_STATEMENT_READY", "Tax / P&L Statement Ready",
        Classification.TRANSACTIONAL, Priority.MEDIUM, False,
        (Channel.EMAIL, Channel.IN_APP)),

    # --- Engagement / promotional (LOW, DND-scrubbed, opt-out respected) -------
    "NEW_FEATURE_ANNOUNCEMENT": EventTypeSpec(
        "NEW_FEATURE_ANNOUNCEMENT", "New Feature Announcement",
        Classification.PROMOTIONAL, Priority.LOW, False,
        (Channel.IN_APP, Channel.PUSH, Channel.EMAIL)),
    "REFERRAL_BONUS_EARNED": EventTypeSpec(
        "REFERRAL_BONUS_EARNED", "Referral Bonus Earned",
        Classification.PROMOTIONAL, Priority.LOW, False,
        (Channel.PUSH, Channel.IN_APP, Channel.WHATSAPP)),
    "MARKET_INSIGHTS_DIGEST": EventTypeSpec(
        "MARKET_INSIGHTS_DIGEST", "Weekly Market Insights",
        Classification.PROMOTIONAL, Priority.LOW, False,
        (Channel.EMAIL, Channel.WHATSAPP)),
    "PORTFOLIO_INACTIVITY_NUDGE": EventTypeSpec(
        "PORTFOLIO_INACTIVITY_NUDGE", "We Miss You - Portfolio Nudge",
        Classification.PROMOTIONAL, Priority.LOW, False,
        (Channel.PUSH, Channel.WHATSAPP)),
    "CROSS_SELL_MUTUAL_FUND": EventTypeSpec(
        "CROSS_SELL_MUTUAL_FUND", "Recommended Mutual Fund Offer",
        Classification.PROMOTIONAL, Priority.LOW, False,
        (Channel.PUSH, Channel.EMAIL, Channel.WHATSAPP)),
}


def get_spec(event_code: str) -> EventTypeSpec:
    try:
        return EVENT_CATALOG[event_code]
    except KeyError as exc:
        raise ValueError(f"Unknown event type: {event_code}") from exc


def all_event_codes() -> list[str]:
    return list(EVENT_CATALOG.keys())
