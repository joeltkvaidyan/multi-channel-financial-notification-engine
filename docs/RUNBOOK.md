# Runbook — Deployment & Monitoring

## 1. Local development (current state of this repo)

```bash
pip install -r requirements.txt
python demo.py                      # exercises all 5 patterns end-to-end
uvicorn app.main:app --reload       # API on http://localhost:8000
streamlit run dashboard.py          # dashboard on http://localhost:8501
pytest tests/ -v                    # 17 tests, ~1 second
```

No external services are required. SQLite file `notification_engine.db`
is created on first run in the project root; delete it to reset state.

## 2. Production deployment topology

```
                    ┌─────────────┐
   Producers  ───►  │   Kafka      │  ──► raw.events (partitioned by user_id)
 (order/risk/KYC/    │   cluster    │
  marketing svcs)    └─────────────┘
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
        Ingestion      Ingestion      Ingestion        (consumer group:
        worker #1      worker #2      worker #3          notification-ingestion,
                                                           horizontally scaled)
              │             │             │
              └─────────────┼─────────────┘
                            ▼
                     Postgres (write model:
                     notifications, delivery_attempts,
                     dead_letters, event_store)
                            │
                            ▼ (separate, lagging consumer group)
                     Postgres (read model:
                     notification_metrics_daily)
                            │
                            ▼
                   Streamlit/BI dashboard
```

### Swapping from demo to production

| Component | Change required |
|---|---|
| Event bus | `app/config.py`: `EVENT_BUS_BACKEND=kafka`, set `KAFKA_BOOTSTRAP_SERVERS`. `app/event_bus.py` already has the `KafkaEventBus` adapter scaffolded — wire consumer-group instantiation. |
| Database | `NOTIFICATION_ENGINE_DB_URL=postgresql://...` env var — `app/database.py` requires no other change. |
| SMS | Implement `ChannelAdapter` in `app/channels/sms_channel.py` against MSG91/Twilio/Karix, replacing `_simulate(...)`. |
| Email | Same pattern, `email_channel.py`, against SendGrid/SES/Postmark. |
| Push | Same pattern, `push_channel.py`, against FCM/APNs via `firebase-admin`. |
| WhatsApp | Same pattern, `whatsapp_channel.py`, against WhatsApp Business Cloud API. **Note:** outside the 24h user-session window, only pre-approved Meta message templates can be sent — template approval lead time should be factored into rollout planning. |
| Secrets | Move provider API keys to a secrets manager (AWS Secrets Manager / Vault), injected as env vars — never hardcoded in adapter classes. |

## 3. Monitoring & alerting

Recommended alerts (none wired up in this demo — listed for the
production rollout):

| Metric | Threshold | Why |
|---|---|---|
| DLQ insert rate | > 1% of `notifications` created in 5 min | Indicates a channel provider outage, not isolated user issues |
| `regulatory_mandatory` notifications in DLQ | **any** | Page on-call immediately — a margin call/KYC alert failed to reach a user on every channel |
| Saga per-channel failure rate | > 10% for any single channel over 15 min | Provider-side incident; consider temporarily deprioritizing that channel in routing |
| Event ingestion consumer lag | > 30s | Ingestion workers falling behind producer rate; scale out |
| Read-model (`notification_metrics_daily`) staleness | > 5 min | Dashboard consumer group stalled |

Expose these via Prometheus counters/gauges from the consumer processes
(`notifications_created_total`, `notifications_dlq_total{event_code,
regulatory_mandatory}`, `channel_send_failures_total{channel}`,
`consumer_lag_seconds`), scraped by the existing observability stack.

## 4. Operational procedures

**Requeueing dead letters.** Once a user's contact info is corrected (or
a provider outage is confirmed resolved), call
`app/dlq/dead_letter_queue.requeue(session, dead_letter_id)` and re-submit
the original payload through `handle_event`. A scheduled sweep job that
auto-requeues DLQ entries once per day (skipping any already
`requeued=True`) is recommended rather than purely manual triage.

**Scaling ingestion for a market-open spike.** Ingestion consumer
instances are stateless and partitioned by `user_id` — scale the consumer
group horizontally ahead of known high-volume windows (market open,
T+1 settlement, dividend record dates) and scale back down after.

**Rolling back a bad template.** Templates are filesystem-based
(`templates/<channel>/<locale>/<event_code>.*`) and loaded per-render —
no caching layer to invalidate. Reverting a template file and redeploying
is sufficient; no notification-engine restart required if templates are
mounted from a shared volume/config-map in production.

**Replaying history for an audit.** Use
`app/event_sourcing/event_store.replay_for_user(session, user_id)` to pull
every raw event for a user in chronological order. Combine with the
`notifications` table (joined on `event_store_id`) to reconstruct exactly
what was decided and sent for each event.
