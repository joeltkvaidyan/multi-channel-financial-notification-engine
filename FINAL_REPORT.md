# Final Project Report
## Multi-Channel Financial Notification Engine
**Zetheta Algorithms — Backend Internship Project**

---

## 1. Problem Statement

A brokerage / wealth-management platform generates a high volume of
events that must reach users reliably across multiple channels —
margin calls, order confirmations, SIP reminders, price alerts, KYC
notices, and marketing communication — while respecting:

- **Regulatory law** (SEBI broker obligations, TRAI's DND/TCCCPR 2018
  regime for promotional messaging),
- **User preference** (channel choice, opt-outs, quiet hours),
- **Operational reality** (channels fail; providers rate-limit; users
  don't all check push notifications).

The core engineering question this project answers: **how do you
guarantee a critical, regulator-mandated alert reaches a user, without
spamming that same user with marketing, and while being able to prove —
months later, to an auditor — exactly what was decided and why for every
single event?**

## 2. System Overview

The engine is event-driven, structured around four architectural patterns
chosen deliberately for the constraints above (full rationale in
`docs/ARCHITECTURE.md §4`):

| Pattern | Where | Why this problem needs it |
|---|---|---|
| **Event Sourcing** | `app/event_sourcing/` | Append-only log of every event = the audit trail a regulated business is required to be able to produce. |
| **CQRS** | `app/cqrs/` | Separates high-throughput ingestion writes from analytics reads, so dashboard queries never contend with live traffic. |
| **Saga** | `app/saga/` | Multi-channel delivery is a multi-step, independently-retryable process with a defined failure path (DLQ) — not a single try/except. |
| **Dead Letter Queue** | `app/dlq/` | Guarantees nothing is silently dropped, with a manual/automated requeue path. |

29 financial event types are catalogued in `app/domain/event_types.py`,
each carrying its own classification (transactional/promotional),
priority, regulatory-mandatory flag, and allowed-channel list — this
single table is the source of truth every downstream module reads from.

## 3. Architecture Diagrams

See `docs/ARCHITECTURE.md` for the full set (rendered as Mermaid, viewable
directly on GitHub):

1. End-to-end event-driven flow (producer → ingestion → compliance →
   preferences → routing → templates → saga → channels → DLQ/analytics)
2. Channel routing decision tree (the exact precedence logic implemented)
3. Saga sequence diagrams for both the successful-fallback case and the
   all-channels-exhausted → DLQ case

## 4. Compliance Implementation

Full detail in `docs/COMPLIANCE.md`. Summary of the two regulatory layers
and how they interact with the routing engine:

- **TRAI DND** (`app/compliance/trai_dnd.py`): applies *only* to
  promotional traffic. DND-registered numbers are blocked from
  promotional sends; all promotional sends additionally respect the
  09:00–21:00 legal window. Transactional traffic bypasses both checks.
- **SEBI mandates** (`app/compliance/sebi.py`): a subset of event types
  (margin calls, trade confirmations, KYC alerts, etc.) are flagged
  `regulatory_mandatory=True`. The preference engine re-inserts channels
  the user opted out of for these events, and the router bypasses quiet
  hours and frequency caps for them — because a margin call cannot
  legally be made undeliverable by a user's notification settings.

This ordering — **regulatory mandate > DND/promotional-window check >
user preference > frequency cap > quiet hours > engagement/cost
reorder** — is enforced as a strict sequence in `app/routing/router.py`,
not as independent flags that could contradict each other.

## 5. Demonstrated Behaviour (from `demo.py`, verified output)

| Scenario | What it proves | Result |
|---|---|---|
| 1. `MARGIN_CALL` at 2 AM, push opted out, quiet hours 22:00–07:00 | Regulatory mandate overrides both quiet hours and channel opt-out | `DELIVERED`, plan included PUSH despite opt-out |
| 2. `SIP_REMINDER`, engagement scores `{PUSH:0.85, WHATSAPP:0.6, SMS:0.3}` | Delivery optimisation reorders by engagement | `DELIVERED` via PUSH (highest engagement) |
| 3. `MARKET_INSIGHTS_DIGEST`, DND-registered user | TRAI DND correctly blocks promotional-only | `SUPPRESSED`, reason `TRAI_DND_REGISTERED_PROMOTIONAL_BLOCKED`, fully audited |
| 4. `ORDER_EXECUTED`, all channel adapters forced to fail | Saga retries each channel (3x, exponential backoff), falls back across the full plan, then dead-letters | `DEAD_LETTERED` after 9 total attempts across 3 channels |
| 5. Bulk run, all 29 event types, one user | CQRS read model accumulates correctly in real time | `/analytics/summary`: 33 created, 29 delivered, 1 failed, 3 suppressed, 1 dead-lettered |

17 automated tests (`pytest tests/ -v`) cover the compliance gate,
preference hierarchy, frequency capping, quiet-hours edge cases (including
the overnight-window case), router composition, and full pipeline
integration — all passing.

## 6. Deliverables Checklist

- [x] GitHub-ready repo structure (this codebase)
- [x] Architecture diagrams — `docs/ARCHITECTURE.md` (4 Mermaid diagrams)
- [x] Modular codebase — notification processor (`cqrs/command_handlers.py`),
      template engine (`templates_engine/`), preference DB schema (`models.py`)
- [x] Sample templates — SMS (2 locales), Email, Push, WhatsApp, In-App
- [x] Compliance documentation — `docs/COMPLIANCE.md`
- [x] Analytics dashboard mockup — `dashboard.py` (Streamlit) + sample
      output in `docs/ANALYTICS_DASHBOARD.md`
- [x] Runbook — `docs/RUNBOOK.md` (deployment topology + monitoring + ops procedures)
- [x] Test suite — 17 tests, `tests/`
- [ ] Transfer to `@ZethetaIntern` on Day 15 — push this repo once reviewed

## 7. Positioning for Evaluation

**Fault tolerance.** The Saga's per-channel exponential backoff and
cross-channel fallback, plus the DLQ's guarantee that nothing is silently
dropped, are demonstrated deterministically in Scenario 4 by forcing a
100% failure rate and observing the full retry/fallback/dead-letter
sequence in the logs.

**Regulatory awareness.** The classification-first design (transactional
vs promotional) and the explicit precedence order (regulatory > DND >
preference > caps) are the parts of this system most likely to be
probed in review — `docs/COMPLIANCE.md` is written to be readable by a
non-engineer compliance reviewer for exactly that reason.

**User experience safeguards.** Quiet hours and frequency capping are
implemented as independent controls (a user could want one without the
other) and are proven, via unit tests, to never apply to regulatory-
mandatory or transactional traffic respectively.

**Scalability.** The event bus is built against an abstract interface
(`EventBus`) with the Kafka adapter scaffolded but not requiring a live
broker for the demo — this is a deliberate "production seam," documented
in `docs/RUNBOOK.md §2`, that lets the same business logic run unmodified
against an in-process queue today and a real Kafka cluster partitioned by
`user_id` tomorrow.

## 8. Known Limitations / Future Work

(Also listed in `docs/COMPLIANCE.md §5` for the compliance-specific items.)

- Promotional messages outside the TRAI window are suppressed rather than
  rescheduled — production should auto-requeue for the next valid window.
- DND registry status is stored as a cached boolean, not a live registry
  lookup — production needs a periodic sync job.
- Channel adapters are mocks with simulated latency/failure rates;
  swapping in real providers (MSG91, SendGrid, FCM, WhatsApp Business API)
  is a one-class-per-channel change, documented in `docs/RUNBOOK.md`.
- No automated DLQ-sweep job is implemented (manual `requeue()` call
  exists; a scheduler around it is noted as the production next step).

---

*Prepared as part of the Zetheta Algorithms backend internship deliverables.
Codebase, tests, and documentation are organised for direct transfer to
`@ZethetaIntern`.*
