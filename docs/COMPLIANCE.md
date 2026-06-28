# Compliance Documentation

This document explains the regulatory logic implemented in
`app/compliance/` and why it's structured the way it is. It is written so
a compliance reviewer (not just an engineer) can audit the rules without
reading code.

## 1. Classification is the first gate: TRANSACTIONAL vs PROMOTIONAL

Every one of the 29 event types in `app/domain/event_types.py` is tagged
with a `classification`:

- **TRANSACTIONAL** — directly related to an existing account
  relationship and a specific transaction or account event: order fills,
  margin calls, payment confirmations, KYC alerts, security alerts.
- **PROMOTIONAL** — marketing/engagement content not tied to a specific
  transaction: feature announcements, market digests, cross-sell offers,
  inactivity nudges.

This distinction matters because **TRAI's DND regulation under TCCCPR
2018 applies only to promotional commercial communication.** Getting this
classification wrong in either direction is a real compliance failure:

- Misclassifying a promotional message as transactional → DND-registered
  users get spammed → regulatory exposure for the business.
- Misclassifying a transactional message as promotional → a margin call
  or KYC suspension notice could be wrongly suppressed for a DND-registered
  user → the user doesn't find out their account/position is at risk.

## 2. TRAI DND handling (`app/compliance/trai_dnd.py`)

For **PROMOTIONAL** traffic only:

1. If the recipient is registered on the DND registry
   (`dnd_registered=True` on their preference row), the message is
   suppressed with reason `TRAI_DND_REGISTERED_PROMOTIONAL_BLOCKED`.
2. Independent of DND registration, promotional messages are only sent
   within the legally permitted window, **09:00–21:00 local time**. Outside
   this window, the message is suppressed with reason
   `OUTSIDE_TRAI_PROMOTIONAL_WINDOW` and is *not* simply delayed in this
   demo (a production system would re-queue it for the next valid window
   rather than drop it — noted as a future enhancement below).

**TRANSACTIONAL** traffic bypasses both checks entirely — `is_dnd_blocked`
returns `(False, None)` immediately for transactional classification.

## 3. SEBI regulatory mandates (`app/compliance/sebi.py`)

A subset of event types are flagged `regulatory_mandatory=True`:

| Event | Why it's mandatory |
|---|---|
| `MARGIN_CALL`, `MARGIN_SHORTFALL_AUTO_LIQUIDATION`, `RISK_LIMIT_BREACH` | Client must be informed of risk to capital/positions |
| `ORDER_EXECUTED`, `ORDER_REJECTED`, `TRADE_CONTRACT_NOTE` | Exchange bye-laws require trade confirmation / contract notes |
| `FUNDS_ADDED`, `FUNDS_WITHDRAWN`, `PAYMENT_FAILED`, `SIP_DEBIT_FAILED` | Financial transaction confirmation |
| `STOP_LOSS_TRIGGERED`, `IPO_ALLOTMENT_STATUS` (allotment is HIGH but not flagged mandatory here — see note) | Position-affecting event |
| `KYC_DOCUMENT_EXPIRING`, `KYC_SUSPENDED`, `LOGIN_NEW_DEVICE`, `PASSWORD_CHANGED` | Account security / regulatory KYC obligations |

For these event types, the channel router **re-inserts** any channel the
user had opted out of (see `preference_engine.resolve_channel_order`),
because a SEBI-mandated alert cannot be made undeliverable purely by user
preference. The router still won't invent a channel the user has no
contact info for — "mandatory" means "do not let preference *suppress*
it", not "magically deliver it with no contact info."

Regulatory-mandatory events also **bypass quiet hours** and **frequency
caps** — a margin call at 2 AM must still go out; it cannot wait until
7 AM, and it cannot be the message that "uses up" a promotional quota.

## 4. Audit trail

Every event — sent, suppressed, or dead-lettered — is durably recorded in
`event_store` (Event Sourcing) **before** any compliance decision is made,
and every suppression carries a machine-readable `suppression_reason`
stored on the `Notification` row. This means a compliance audit can answer,
for any user and any date: *what events occurred, what we decided to do
about each one, and why* — without relying on logs that might have rotated
out.

## 5. Known simplifications in this demo (and the production fix)

- **Promotional messages outside the TRAI window are suppressed, not
  rescheduled.** Production fix: re-publish to a delayed queue
  (Kafka topic with a scheduled-delivery consumer, or a simple
  `next_eligible_send_at` column) so the message sends automatically at
  09:00 the next valid day instead of being lost.
- **DND registry status is a boolean on the preference row**, not a live
  lookup against the TRAI/operator DND API. Production fix: periodic sync
  job against the telecom DND registry (numbers can register/de-register),
  with the boolean treated as a cache.
- **No consent-management audit for WhatsApp Business opt-in**, which Meta
  requires separately from TRAI DND. Production fix: a dedicated
  `whatsapp_opt_in_status` field with its own audit trail, since
  WhatsApp's 24-hour session-window and template-approval rules are a
  distinct compliance surface from TRAI.
