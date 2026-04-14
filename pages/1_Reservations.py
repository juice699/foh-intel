"""
FOH Intel — Reservations
Full reservation timeline with status tracking, party info, VIP flags,
preferences, and wait-time visibility.
"""
import streamlit as st
import pandas as pd

from foh.dashboard_utils import (
    init_session_state, render_sim_sidebar, is_standalone,
    load_floor_data, get_sim_time, sim_time_label, maybe_advance_sim,
)

st.set_page_config(page_title="Reservations | FOH Intel", layout="wide", page_icon="📋")
init_session_state()
render_sim_sidebar("Reservations")

date_str  = st.session_state["sim_date"].strftime("%Y-%m-%d")
mode      = st.session_state["data_mode"]
sim_time  = get_sim_time()
sim_iso   = sim_time.isoformat() if sim_time else None

st.title("Reservations")
if sim_time:
    st.caption(f"Simulating **{sim_time_label()}** · {date_str}")

with st.spinner("Loading…"):
    try:
        servers, checks, shifts, reservations = load_floor_data(
            date_str, mode, sim_iso, is_standalone()
        )
    except Exception as e:
        st.error(f"Pipeline error: {e}")
        st.stop()

# ---------------------------------------------------------------------------
# Status summary bar
# ---------------------------------------------------------------------------

upcoming  = [r for r in reservations if r.status.value == "booked"]
seated    = [r for r in reservations if r.status.value == "seated"]
completed = [r for r in reservations if r.status.value == "completed"]
no_shows  = [r for r in reservations if r.status.value == "no_show"]
vips      = [r for r in reservations if r.is_vip]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Upcoming",  len(upcoming))
c2.metric("Seated",    len(seated))
c3.metric("Completed", len(completed))
c4.metric("No-Shows",  len(no_shows))
c5.metric("VIPs",      len(vips))

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

st.divider()

fcol1, fcol2, fcol3 = st.columns([2, 1, 1])
with fcol1:
    status_filter = st.multiselect(
        "Filter by Status",
        ["Booked", "Seated", "Completed", "No Show"],
        default=["Booked", "Seated"],
    )
with fcol2:
    vip_only = st.checkbox("VIP only")
with fcol3:
    sort_by = st.selectbox("Sort by", ["Time", "Party Size", "Status"])

# ---------------------------------------------------------------------------
# Build and filter table
# ---------------------------------------------------------------------------

STATUS_DISPLAY = {
    "booked":    "Booked",
    "seated":    "Seated",
    "completed": "Completed",
    "no_show":   "No Show",
}

rows = []
for r in reservations:
    status_disp = STATUS_DISPLAY.get(r.status.value, r.status.value)
    if status_filter and status_disp not in status_filter:
        continue
    if vip_only and not r.is_vip:
        continue

    prefs = ", ".join(p.value.replace("_", " ") for p in r.preferences) if r.preferences else ""
    server_map = {s.provider_id: s.name for s in servers}
    assigned = server_map.get(r.server_id, "—") if r.server_id else "—"

    rows.append({
        "Time":       r.scheduled_at.strftime("%I:%M %p"),
        "Guest":      r.guest_name,
        "Party":      r.party_size,
        "Status":     status_disp,
        "VIP":        "★" if r.is_vip else "",
        "Wait (min)": f"{r.wait_minutes:.0f}" if r.wait_minutes is not None else "—",
        "Server":     assigned,
        "Table":      r.table_id or "—",
        "Preferences": prefs,
        "Notes":      r.notes or "",
    })

if sort_by == "Party Size":
    rows.sort(key=lambda x: x["Party"], reverse=True)
elif sort_by == "Status":
    order = {"Seated": 0, "Booked": 1, "Completed": 2, "No Show": 3}
    rows.sort(key=lambda x: order.get(x["Status"], 99))
# Default: already sorted by time from generator

df = pd.DataFrame(rows) if rows else pd.DataFrame()

if not df.empty:
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Party": st.column_config.NumberColumn(width="small"),
            "VIP":   st.column_config.TextColumn(width="small"),
            "Wait (min)": st.column_config.TextColumn(width="small"),
        },
    )
else:
    st.info("No reservations match the current filter.")

# ---------------------------------------------------------------------------
# Party size distribution
# ---------------------------------------------------------------------------

if reservations:
    st.divider()
    st.subheader("Party Size Distribution")
    size_counts = {}
    for r in reservations:
        size_counts[r.party_size] = size_counts.get(r.party_size, 0) + 1
    df_sizes = pd.DataFrame(
        [{"Party Size": k, "Reservations": v} for k, v in sorted(size_counts.items())]
    ).set_index("Party Size")
    st.bar_chart(df_sizes, height=200)

# ---------------------------------------------------------------------------
# VIP detail cards
# ---------------------------------------------------------------------------

vip_res = [r for r in reservations if r.is_vip]
if vip_res:
    st.divider()
    st.subheader(f"VIP Guests ({len(vip_res)})")
    for r in vip_res:
        status_disp = STATUS_DISPLAY.get(r.status.value, r.status.value)
        prefs = ", ".join(p.value.replace("_", " ") for p in r.preferences) if r.preferences else "None noted"
        col_badge = {"Seated": "🟢", "Booked": "🔵", "Completed": "⚫", "No Show": "🔴"}
        badge = col_badge.get(status_disp, "")
        with st.container(border=True):
            h1, h2 = st.columns([3, 1])
            with h1:
                st.markdown(f"**{badge} {r.guest_name}** · Party of {r.party_size}")
            with h2:
                st.markdown(f"**{r.scheduled_at.strftime('%I:%M %p')}** · {status_disp}")
            if r.notes:
                st.caption(f"Note: {r.notes}")
            st.caption(f"Preferences: {prefs}")

maybe_advance_sim()
