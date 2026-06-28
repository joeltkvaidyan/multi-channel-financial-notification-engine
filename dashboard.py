"""
Analytics dashboard — the CQRS read side, visualised.

Reads exclusively from `app/database.py` query helpers, which in turn read
the denormalized `NotificationMetricsDaily` table — never the write-model
tables directly. This is what "the dashboard never competes with
ingestion for locks" looks like in practice.

Run: streamlit run dashboard.py   (after running demo.py at least once so
there's data to show)
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from app.cqrs import query_handlers as q
from app.database import get_session, init_db

st.set_page_config(page_title="Notification Engine — Analytics", layout="wide")
init_db()

st.title("📡 Multi-Channel Notification Engine — Analytics Dashboard")
st.caption("CQRS read side · reads from the pre-aggregated metrics table, isolated from ingestion writes")

with get_session() as session:
    summary = q.delivery_summary(session)
    by_channel = q.breakdown_by_channel(session)
    by_event = q.breakdown_by_event_type(session)
    dead_letters = q.recent_dead_letters(session, limit=25)

# ---------------------------------------------------------------------------
# Top-line KPIs
# ---------------------------------------------------------------------------
cols = st.columns(6)
labels = ["Created", "Sent", "Delivered", "Failed", "Suppressed", "Dead-lettered"]
keys = ["created", "sent", "delivered", "failed", "suppressed", "dead_lettered"]
for col, label, key in zip(cols, labels, keys):
    col.metric(label, summary.get(key, 0))

if summary["created"] > 0:
    delivery_rate = round(100 * summary["delivered"] / summary["created"], 1)
    st.progress(min(delivery_rate / 100, 1.0), text=f"Overall delivery rate: {delivery_rate}%")

st.divider()

# ---------------------------------------------------------------------------
# Channel breakdown
# ---------------------------------------------------------------------------
left, right = st.columns(2)

with left:
    st.subheader("Delivery by Channel")
    if by_channel:
        df = pd.DataFrame(by_channel)
        fig = px.bar(df, x="channel", y=["delivered", "failed"], barmode="group",
                     color_discrete_map={"delivered": "#2e7d32", "failed": "#d32f2f"})
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No data yet — run `python demo.py` first.")

with right:
    st.subheader("Volume by Event Type")
    if by_event:
        df = pd.DataFrame(by_event).sort_values("created", ascending=False).head(15)
        fig = px.bar(df, x="created", y="event_code", orientation="h",
                     color="suppressed", color_continuous_scale="Reds")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No data yet — run `python demo.py` first.")

st.divider()

# ---------------------------------------------------------------------------
# DLQ / ops visibility
# ---------------------------------------------------------------------------
st.subheader("☠️ Dead Letter Queue — Recent Entries")
st.caption("Notifications where every channel in the plan exhausted retries. Requires manual review.")
if dead_letters:
    st.dataframe(pd.DataFrame(dead_letters), use_container_width=True)
else:
    st.success("No dead letters. Every notification reached at least one channel.")

st.divider()
st.caption(f"Data as of {date.today().isoformat()} · Notification Engine v1.0 · Zetheta Algorithms internship project")
