"""
FOH Intel — Home
Quick service-at-a-glance: key metrics, server scores, active floor counts.
Use the sidebar to set date, mode, and simulator time.
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timezone

from foh.dashboard_utils import (
    init_session_state, render_sim_sidebar, is_standalone,
    load_floor_data, get_sim_time, sim_time_label, maybe_advance_sim,
)
from foh.scoring.engine import build_profiles

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="FOH Intel",
    page_icon="🍽",
    layout="wide",
)

init_session_state()
render_sim_sidebar("FOH Intel")

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

date_str  = st.session_state["sim_date"].strftime("%Y-%m-%d")
mode      = st.session_state["data_mode"]
sim_time  = get_sim_time()
sim_iso   = sim_time.isoformat() if sim_time else None
standalone = is_standalone()

st.title("FOH Intel — Service Overview")
if sim_time:
    st.caption(f"Simulated floor state · **{sim_time_label()}** on {date_str}")
else:
    st.caption(f"Live · {datetime.now().strftime('%I:%M:%S %p')} · {date_str}")

with st.spinner("Loading floor data…"):
    try:
        servers, checks, shifts, reservations = load_floor_data(
            date_str, mode, sim_iso, standalone
        )
    except Exception as e:
        st.error(f"Pipeline error: {e}")
        st.stop()

# ---------------------------------------------------------------------------
# Key metrics row
# ---------------------------------------------------------------------------

closed   = [c for c in checks if c.closed_at]
open_    = [c for c in checks if not c.closed_at]
upcoming = [r for r in reservations if r.status.value == "booked"]
seated   = [r for r in reservations if r.status.value == "seated"]
on_floor = [s for s in shifts if not s.clock_out]
vips_now = [r for r in reservations if r.is_vip and r.status.value in ("booked", "seated")]

avg_turn = sum(c.turn_time_minutes for c in closed) / len(closed) if closed else 0
avg_tip  = (
    sum(c.tip_percentage for c in closed if c.tip_percentage) /
    max(len([c for c in closed if c.tip_percentage]), 1)
) if closed else 0

m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
m1.metric("Servers On Floor", len(on_floor))
m2.metric("Open Tables",      len(open_))
m3.metric("Checks Closed",    len(closed))
m4.metric("Booked / Upcoming", len(upcoming))
m5.metric("Currently Seated", len(seated))
m6.metric("Avg Turn",         f"{avg_turn:.0f} min")
m7.metric("Avg Tip",          f"{avg_tip:.1f}%")

# ---------------------------------------------------------------------------
# Server score summary
# ---------------------------------------------------------------------------

st.divider()
st.subheader("Server Scores")

profiles = build_profiles(servers, checks, shifts)

if profiles:
    server_map = {s.provider_id: s.name for s in servers}
    rows = []
    for p in sorted(profiles, key=lambda x: x.performance_score, reverse=True):
        rows.append({
            "Server":       p.server.name,
            "Score":        p.performance_score,
            "Tables Done":  p.check_count,
            "Open":         p.open_tables,
            "Covers (open)": p.open_covers,
            "Avg Tip %":    round(p.avg_tip_pct, 1),
            "Avg Turn":     f"{p.avg_turn_minutes:.0f} min" if p.avg_turn_minutes else "—",
        })
    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Score": st.column_config.ProgressColumn(
                "Score", min_value=0.0, max_value=1.0, format="%.2f"
            ),
        },
    )
else:
    st.info("No shift data yet — scores will appear once servers clock in.")

# ---------------------------------------------------------------------------
# Upcoming VIPs alert
# ---------------------------------------------------------------------------

if vips_now:
    st.divider()
    st.subheader("VIP Alert")
    for r in vips_now:
        status_badge = "Seated" if r.status.value == "seated" else "Arriving"
        notes = f" · {r.notes}" if r.notes else ""
        prefs = ", ".join(p.value for p in r.preferences) if r.preferences else ""
        pref_str = f" · Prefers: {prefs}" if prefs else ""
        st.warning(
            f"★ **{r.guest_name}** — Party of {r.party_size} · "
            f"{r.scheduled_at.strftime('%I:%M %p')} · {status_badge}{notes}{pref_str}"
        )

# ---------------------------------------------------------------------------
# Auto-advance
# ---------------------------------------------------------------------------

maybe_advance_sim()
