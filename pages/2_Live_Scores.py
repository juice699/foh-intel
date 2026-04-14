"""
FOH Intel — Live Scores
Server performance scores that update in real time as the simulation advances.
Includes score trend chart, per-server metric breakdown, and shift status.
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timezone

from foh.dashboard_utils import (
    init_session_state, render_sim_sidebar, is_standalone,
    load_floor_data, get_sim_time, sim_time_label, maybe_advance_sim,
    SERVICE_START_HOUR, STEP_MINUTES,
)
from foh.scoring.engine import build_profiles

st.set_page_config(page_title="Live Scores | FOH Intel", layout="wide", page_icon="📊")
init_session_state()
render_sim_sidebar("Live Scores")

date_str   = st.session_state["sim_date"].strftime("%Y-%m-%d")
mode       = st.session_state["data_mode"]
sim_time   = get_sim_time()
sim_iso    = sim_time.isoformat() if sim_time else None
standalone = is_standalone()
cur_step   = st.session_state["sim_step"]

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.title("Live Server Scores")
if st.session_state.get("sim_active"):
    running = st.session_state.get("sim_running", False)
    st.caption(
        f"{'▶ Playing' if running else '⏸ Paused'} · "
        f"Simulated **{sim_time_label()}** · Use sidebar controls to play/pause/scrub"
    )
else:
    st.caption(f"Real-time · {datetime.now().strftime('%I:%M:%S %p')}")

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

with st.spinner("Scoring…"):
    try:
        servers, checks, shifts, reservations = load_floor_data(
            date_str, mode, sim_iso, standalone
        )
    except Exception as e:
        st.error(f"Pipeline error: {e}")
        st.stop()

profiles = build_profiles(servers, checks, shifts)

# ---------------------------------------------------------------------------
# Record score snapshot for trend chart
# ---------------------------------------------------------------------------

history: dict = st.session_state.get("score_history", {})
if profiles:
    history[cur_step] = {
        p.server.provider_id: {
            "name":   p.server.name,
            "score":  p.performance_score,
            "tables": p.check_count,
            "open":   p.open_tables,
        }
        for p in profiles
    }
    st.session_state["score_history"] = history

# ---------------------------------------------------------------------------
# Score cards — one per active server
# ---------------------------------------------------------------------------

if profiles:
    sorted_profiles = sorted(profiles, key=lambda p: p.performance_score, reverse=True)
    cols = st.columns(min(len(sorted_profiles), 4))

    for i, p in enumerate(sorted_profiles):
        col = cols[i % 4]
        with col:
            with st.container(border=True):
                # Score meter
                pct = int(p.performance_score * 100)
                delta_str = ""
                # Compute delta vs 2 steps ago if available
                prev_step = cur_step - 2
                if prev_step in history and p.server.provider_id in history[prev_step]:
                    prev_score = history[prev_step][p.server.provider_id]["score"]
                    delta = p.performance_score - prev_score
                    if abs(delta) >= 0.01:
                        delta_str = f"+{delta:.0%}" if delta > 0 else f"{delta:.0%}"

                st.metric(
                    label=p.server.name,
                    value=f"{pct}%",
                    delta=delta_str if delta_str else None,
                )
                st.progress(p.performance_score)

                # Detail rows
                status = "On floor" if not any(
                    sh.clock_out is None and sh.server_id == p.server.provider_id
                    for sh in shifts
                ) else "On floor"
                # Check if clocked out
                clocked_out = all(
                    sh.clock_out is not None
                    for sh in shifts
                    if sh.server_id == p.server.provider_id
                )

                rows_detail = [
                    ("Tables closed",   str(p.check_count)),
                    ("Open tables",     str(p.open_tables)),
                    ("Open covers",     str(p.open_covers)),
                    ("Avg tip",         f"{p.avg_tip_pct:.1f}%" if p.avg_tip_pct else "—"),
                    ("Avg turn",        f"{p.avg_turn_minutes:.0f} min" if p.avg_turn_minutes else "—"),
                    ("Rev / cover",     f"${p.avg_revenue_cover:.2f}" if p.avg_revenue_cover else "—"),
                    ("Status",          "Clocked out" if clocked_out else "On floor"),
                ]
                for label, val in rows_detail:
                    r1, r2 = st.columns([2, 1])
                    r1.caption(label)
                    r2.caption(f"**{val}**")

    # ---------------------------------------------------------------------------
    # Score trend chart
    # ---------------------------------------------------------------------------

    if len(history) >= 2:
        st.divider()
        st.subheader("Score Trend")

        trend_rows = []
        for step_key in sorted(history.keys()):
            offset_min = step_key * STEP_MINUTES
            h = SERVICE_START_HOUR + offset_min // 60
            m = offset_min % 60
            label_h = h if h <= 12 else h - 12
            ampm = "PM" if 12 <= h < 24 else "AM"
            time_label = f"{label_h}:{m:02d} {ampm}"
            for sid, data in history[step_key].items():
                trend_rows.append({
                    "Time":   time_label,
                    "Server": data["name"],
                    "Score":  data["score"],
                })

        df_trend = pd.DataFrame(trend_rows)
        if not df_trend.empty:
            df_pivot = df_trend.pivot_table(
                index="Time", columns="Server", values="Score", aggfunc="last"
            )
            st.line_chart(df_pivot, height=280)

    # ---------------------------------------------------------------------------
    # Full stats table
    # ---------------------------------------------------------------------------

    st.divider()
    st.subheader("Full Metrics Table")

    table_rows = []
    for p in sorted_profiles:
        upsell_count = sum(
            1 for c in checks if c.server_id == p.server.provider_id
            for it in c.items if it.is_upsell
        )
        total_items = sum(
            len(c.items) for c in checks if c.server_id == p.server.provider_id
        )
        upsell_rate = f"{upsell_count/total_items*100:.0f}%" if total_items else "—"

        table_rows.append({
            "Server":        p.server.name,
            "Score":         p.performance_score,
            "Tables Closed": p.check_count,
            "Open Tables":   p.open_tables,
            "Total Covers":  p.total_covers,
            "Avg Tip %":     round(p.avg_tip_pct, 1),
            "Turn Stdev":    round(p.turn_stdev, 1),
            "Avg Turn (min)": round(p.avg_turn_minutes, 1) if p.avg_turn_minutes else 0,
            "Rev / Cover":   round(p.avg_revenue_cover, 2),
            "Upsell Rate":   upsell_rate,
        })

    st.dataframe(
        pd.DataFrame(table_rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Score": st.column_config.ProgressColumn(
                "Score", min_value=0.0, max_value=1.0, format="%.2f"
            ),
        },
    )

else:
    st.info("Scores will appear once servers have closed at least one table.")

# ---------------------------------------------------------------------------
# Auto-advance
# ---------------------------------------------------------------------------

maybe_advance_sim()
