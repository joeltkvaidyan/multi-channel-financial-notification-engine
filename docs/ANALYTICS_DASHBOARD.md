# Analytics Dashboard — Mockup & Sample Output

The live mockup is `dashboard.py` (Streamlit, CQRS read side). Run it with:

```bash
python demo.py            # populate sample data
streamlit run dashboard.py
```

## Layout

1. **Top-line KPIs** — six metrics in a row: Created, Sent, Delivered,
   Failed, Suppressed, Dead-lettered, plus an overall delivery-rate
   progress bar.
2. **Delivery by Channel** (grouped bar chart) — delivered vs failed per
   channel, so a provider-specific outage (e.g. Push) is visually obvious.
3. **Volume by Event Type** (horizontal bar chart) — top 15 event types by
   volume, colour-intensity-coded by suppression count, so high-suppression
   event types stand out for review.
4. **Dead Letter Queue table** — every unresolved dead letter with reason,
   user, event type, and requeue status, for ops triage.

## Sample output (from `python demo.py`, scenario 5 — bulk run across all 29 event types)

```
/analytics/summary  ->
{
  "created": 33, "sent": 0, "delivered": 29, "failed": 1,
  "suppressed": 3, "dead_lettered": 1
}

/analytics/by-channel ->
  EMAIL    created=2   delivered=2   failed=0
  IN_APP   created=9   delivered=9   failed=0
  PUSH     created=19  delivered=18  failed=1
  (NONE: 3 — suppressed before any channel was attempted: TRAI DND /
   outside promotional window)
```

This matches expectations: PUSH carries the most volume (it's the default
first channel for the most common event types) and also shows the highest
failure count, consistent with its configured 18% mock failure rate
representing real-world push deliverability (disabled permissions, stale
device tokens) — exactly the kind of channel-reliability signal a real
ops team would want surfaced on a dashboard.

## Why CQRS matters here in practice

Every chart above reads from `notification_metrics_daily`
(`app/cqrs/query_handlers.py`), never from the live `notifications`
table. During a real market-open spike, ingestion could be writing
thousands of rows/second to `notifications` — an analyst refreshing this
dashboard never competes for a write lock on that table.
