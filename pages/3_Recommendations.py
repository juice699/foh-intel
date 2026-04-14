"""
FOH Intel — Seating Recommendations
Shows the engine's top server suggestions for each upcoming and active reservation.
Updates automatically as the simulation advances — recommendations evolve as
floor load, server performance, and party composition change.
"""
import streamlit as st
import pandas as pd

from foh.dashboard_utils import (
    init_session_state, render_sim_sidebar, is_standalone,
    load_floor_data, get_sim_time, sim_time_label, maybe_advance_sim,
)
from foh.scoring.engine import build_profiles, recommend

st.set_page_config(page_title="Recommendations | FOH Intel", layout="wide", page_icon="🎯")
init_session_state()
render_sim_sidebar("Recommendations")

date_str   = st.session_state["sim_date"].strftime("%Y-%m-%d")
mode       = st.session_state["data_mode"]
sim_time   = get_sim_time()
sim_iso    = sim_time.isoformat() if sim_time else None
standalone = is_standalone()

st.title("Seating Recommendations")
if sim_time:
    st.caption(f"Simulating **{sim_time_label()}** — recommendations update as floor state changes")

with st.spinner("Loading…"):
    try:
        servers, checks, shifts, reservations = load_floor_data(
            date_str, mode, sim_iso, standalone
        )
    except Exception as e:
        st.error(f"Pipeline error: {e}")
        st.stop()

profiles = build_profiles(servers, checks, shifts)

if not profiles:
    st.info("Scoring requires at least one server to be on shift.")
    st.stop()

# ---------------------------------------------------------------------------
# Filter controls
# ---------------------------------------------------------------------------

fcol1, fcol2 = st.columns([2, 1])
with fcol1:
    show_statuses = st.multiselect(
        "Show reservations with status",
        ["Booked", "Seated"],
        default=["Booked"],
    )
with fcol2:
    top_n = st.slider("Recommendations per party", min_value=1, max_value=5, value=3)

STATUS_MAP_REV = {
    "booked":    "Booked",
    "seated":    "Seated",
    "completed": "Completed",
    "no_show":   "No Show",
}

target_res = [
    r for r in reservations
    if STATUS_MAP_REV.get(r.status.value, "") in show_statuses
]

# Sort: VIPs first, then by time
target_res.sort(key=lambda r: (not r.is_vip, r.scheduled_at))

# ---------------------------------------------------------------------------
# Summary metrics
# ---------------------------------------------------------------------------

upcoming_count = len([r for r in reservations if r.status.value == "booked"])
seated_count   = len([r for r in reservations if r.status.value == "seated"])
vip_count      = len([r for r in target_res if r.is_vip])

s1, s2, s3 = st.columns(3)
s1.metric("Upcoming (Booked)", upcoming_count)
s2.metric("Currently Seated",  seated_count)
s3.metric("VIPs in Queue",     vip_count)

# ---------------------------------------------------------------------------
# Recommendation cards
# ---------------------------------------------------------------------------

st.divider()

if not target_res:
    st.info("No reservations match the current filter.")
else:
    for res in target_res:
        suggestions = recommend(res, profiles, top_n=top_n)

        vip_tag   = " ★ VIP" if res.is_vip else ""
        wait_note = ""
        if res.wait_minutes is not None and res.wait_minutes > 5:
            wait_note = f"  ⚠ {res.wait_minutes:.0f} min wait"

        prefs = ", ".join(p.value.replace("_", " ") for p in res.preferences) if res.preferences else ""

        with st.container(border=True):
            # Header row
            hcol1, hcol2 = st.columns([4, 1])
            with hcol1:
                st.markdown(
                    f"**{res.guest_name}**{vip_tag} · "
                    f"Party of {res.party_size} · "
                    f"{res.scheduled_at.strftime('%I:%M %p')}{wait_note}"
                )
                if res.notes:
                    st.caption(f"Note: {res.notes}")
                if prefs:
                    st.caption(f"Preferences: {prefs}")
            with hcol2:
                status_badge = {
                    "booked":    "🔵 Booked",
                    "seated":    "🟢 Seated",
                    "completed": "⚫ Done",
                    "no_show":   "🔴 No Show",
                }
                st.markdown(status_badge.get(res.status.value, res.status.value))

            # Suggestion columns
            if suggestions:
                sug_cols = st.columns(len(suggestions))
                medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
                for col, sug in zip(sug_cols, suggestions):
                    with col:
                        medal = medals[sug.rank - 1] if sug.rank <= len(medals) else f"#{sug.rank}"
                        st.metric(
                            label=f"{medal} {sug.server.name}",
                            value=f"{sug.match_score:.0%}",
                        )
                        for line in sug.reasoning:
                            st.caption(f"• {line}")
            else:
                st.caption("No servers available for recommendation.")

# ---------------------------------------------------------------------------
# Server availability summary
# ---------------------------------------------------------------------------

st.divider()
st.subheader("Server Availability")

avail_rows = []
for p in sorted(profiles, key=lambda x: x.open_covers):
    avail_rows.append({
        "Server":       p.server.name,
        "Score":        p.performance_score,
        "Open Tables":  p.open_tables,
        "Open Covers":  p.open_covers,
        "Status":       "Available" if p.open_tables == 0 else
                        "Light" if p.open_tables <= 2 else "Busy",
    })

st.dataframe(
    pd.DataFrame(avail_rows),
    use_container_width=True,
    hide_index=True,
    column_config={
        "Score": st.column_config.ProgressColumn(
            "Score", min_value=0.0, max_value=1.0, format="%.2f"
        ),
    },
)

maybe_advance_sim()
