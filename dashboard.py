"""
FOH Intel — Development Dashboard
Visualizes live pipeline data for scoring engine development and iteration.

Run locally (requires mock servers):
    streamlit run dashboard.py

Run standalone / Streamlit Community Cloud (no servers needed):
    STANDALONE=true streamlit run dashboard.py
"""
import asyncio
import os
import pandas as pd
import streamlit as st
from datetime import datetime, timezone, timedelta
from foh.providers.factory import get_pos_provider, get_reservation_provider, env_label
from foh.config import settings


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="FOH Intel Dashboard",
    page_icon="🍽",
    layout="wide",
)

def _mock_servers_reachable() -> bool:
    """Quick TCP check — if mock servers aren't up, fall back to standalone."""
    import socket
    for port in (settings.toast_mock_port, settings.opentable_mock_port):
        try:
            with socket.create_connection(("localhost", port), timeout=1):
                pass
        except OSError:
            return False
    return True

IS_STANDALONE = (
    os.getenv("STANDALONE", "false").lower() == "true"
    or settings.standalone
    or not _mock_servers_reachable()
)

st.title("FOH Intel — Development Dashboard")
env_note = "STANDALONE (demo)" if IS_STANDALONE else env_label()
st.caption(f"Environment: **{env_note}** · Data mode: **{settings.data_mode.upper()}**")


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------

col_date, col_mode, col_refresh = st.columns([2, 1, 1])

with col_date:
    selected_date = st.date_input("Service Date", value=datetime.today())

with col_mode:
    mode_override = st.selectbox("Data Mode", ["live", "batch"], index=0)

with col_refresh:
    st.write("")
    refresh = st.button("Refresh", use_container_width=True)

os.environ["DATA_MODE"] = mode_override


# ---------------------------------------------------------------------------
# Simulator — time scrubber for live mode testing
# ---------------------------------------------------------------------------

SERVICE_START_HOUR = 17   # 5:00 PM
SERVICE_END_HOUR   = 23   # 11:00 PM
STEP_MINUTES       = 15
TOTAL_STEPS        = (SERVICE_END_HOUR - SERVICE_START_HOUR) * 60 // STEP_MINUTES  # 24

with st.expander("Runtime Simulator", expanded=(mode_override == "live")):
    sim_col1, sim_col2 = st.columns([1, 3])
    with sim_col1:
        sim_mode = st.radio(
            "Time Source",
            ["Live (now)", "Simulated"],
            index=0,
            help="Simulated: scrub through service to any point in time",
        )
    with sim_col2:
        sim_step = st.slider(
            "Simulated Time",
            min_value=0,
            max_value=TOTAL_STEPS,
            value=TOTAL_STEPS // 2,
            step=1,
            format="%d",
            disabled=(sim_mode == "Live (now)"),
            help="Drag to move through service (5 PM → 11 PM, 15-min steps)",
        )
        # Build a readable label for the slider position
        sim_offset_min = sim_step * STEP_MINUTES
        sim_hour = SERVICE_START_HOUR + sim_offset_min // 60
        sim_min  = sim_offset_min % 60
        sim_label_hour = sim_hour if sim_hour <= 12 else sim_hour - 12
        sim_label_ampm = "PM" if sim_hour < 24 else "AM"
        st.caption(f"Simulated time: **{sim_label_hour}:{sim_min:02d} {sim_label_ampm}**")

# Resolve sim_time
if sim_mode == "Simulated":
    sim_time: datetime | None = datetime(
        selected_date.year, selected_date.month, selected_date.day,
        tzinfo=timezone.utc,
    ) + timedelta(hours=SERVICE_START_HOUR, minutes=sim_step * STEP_MINUTES)
    st.info(
        f"Simulating floor state at **{sim_label_hour}:{sim_min:02d} {sim_label_ampm}** "
        f"on {selected_date.strftime('%b %d, %Y')} — data frozen at this moment."
    )
else:
    sim_time = None


# ---------------------------------------------------------------------------
# Data loading — two paths: standalone (in-process) or HTTP providers
# ---------------------------------------------------------------------------

def _standalone_load(date_str: str, mode: str, sim_time_iso: str | None):
    """
    Generate data entirely in-process using the mock data generators.
    No HTTP servers required — safe for Streamlit Community Cloud.
    sim_time_iso is an ISO string (or None) so it's hashable for @st.cache_data.
    """
    from mock_servers.toast.data import (
        generate_employees, generate_shifts, generate_orders,
    )
    from mock_servers.opentable.data import generate_reservations
    from foh.models.pos import Server, Check, Shift, OrderStatus
    from foh.models.reservations import Reservation, ReservationStatus, DiningPreference
    from decimal import Decimal

    sim_time = (
        datetime.fromisoformat(sim_time_iso) if sim_time_iso else None
    )
    date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    # Employees → Server models
    raw_emps = generate_employees()
    servers = [
        Server(
            provider_id=e["guid"],
            name=f"{e['firstName']} {e['lastName']}",
            email=e.get("email"),
            active=not e.get("deleted", False),
        )
        for e in raw_emps
    ]

    # Shifts
    raw_shifts = generate_shifts(date, mode, sim_time=sim_time)
    shifts = [
        Shift(
            provider_id=s["guid"],
            server_id=s["employeeReference"]["guid"],
            date=datetime.fromisoformat(s["inDate"].replace("Z", "+00:00")),
            clock_in=datetime.fromisoformat(s["inDate"].replace("Z", "+00:00")),
            clock_out=datetime.fromisoformat(s["outDate"].replace("Z", "+00:00"))
                if s.get("outDate") else None,
        )
        for s in raw_shifts
    ]

    # Orders → Checks
    start = date
    end   = date.replace(hour=23, minute=59, second=59)
    raw_orders = generate_orders(start, end, mode, sim_time=sim_time)
    checks = []
    for order in raw_orders:
        for chk in order.get("checks", []):
            payments = chk.get("payments", [])
            tip = sum(Decimal(str(p.get("tipAmount", 0))) for p in payments)
            checks.append(Check(
                provider_id=chk["guid"],
                server_id=order["server"]["guid"],
                table_id=order["table"]["guid"],
                opened_at=datetime.fromisoformat(order["openedDate"].replace("Z", "+00:00")),
                closed_at=datetime.fromisoformat(order["closedDate"].replace("Z", "+00:00"))
                    if order.get("closedDate") else None,
                covers=order.get("numberOfGuests", 0),
                subtotal=Decimal(str(chk.get("amount", 0))),
                tax=Decimal(str(chk.get("taxAmount", 0))),
                tip=tip if tip > 0 else None,
                status=OrderStatus.CLOSED if order.get("closedDate") else OrderStatus.OPEN,
            ))

    # Reservations
    PREF_MAP = {
        "window": DiningPreference.WINDOW, "booth": DiningPreference.BOOTH,
        "bar": DiningPreference.BAR, "patio": DiningPreference.PATIO,
        "quiet section": DiningPreference.QUIET, "high chair": DiningPreference.HIGH_CHAIR,
        "wheelchair accessible": DiningPreference.ACCESSIBLE,
    }
    STATUS_MAP = {
        "booked": ReservationStatus.BOOKED, "seated": ReservationStatus.SEATED,
        "completed": ReservationStatus.COMPLETED, "no_show": ReservationStatus.NO_SHOW,
    }
    raw_res = generate_reservations(date, mode, sim_time=sim_time)
    reservations = [
        Reservation(
            provider_id=r["id"],
            guest_id=r.get("guestId"),
            guest_name=r["guestName"],
            party_size=r["partySize"],
            scheduled_at=datetime.fromisoformat(r["dateTime"]),
            seated_at=datetime.fromisoformat(r["seatedAt"]) if r.get("seatedAt") else None,
            status=STATUS_MAP.get(r["status"], ReservationStatus.BOOKED),
            table_id=r.get("tableId"),
            server_id=r.get("serverId"),
            notes=r.get("notes"),
            preferences=[PREF_MAP[p] for p in r.get("specialRequests", []) if p in PREF_MAP],
            is_vip=r.get("isVip", False),
        )
        for r in raw_res
    ]

    return servers, checks, shifts, reservations


@st.cache_data(ttl=15, show_spinner=False)
def load_data(date_str: str, mode: str, env: str, standalone: bool, sim_time_iso: str | None):
    """Cached 15s — auto-refreshes in live mode to reflect floor changes."""
    if standalone:
        return _standalone_load(date_str, mode, sim_time_iso)

    date = datetime.strptime(date_str, "%Y-%m-%d")

    async def _fetch():
        pos = get_pos_provider()
        await pos.authenticate()
        servers = await pos.get_servers()
        checks  = await pos.get_checks(date)
        shifts  = await pos.get_shifts(date)

        res          = get_reservation_provider()
        await res.authenticate()
        reservations = await res.get_reservations(date)
        return servers, checks, shifts, reservations

    return asyncio.run(_fetch())


sim_time_iso = sim_time.isoformat() if sim_time else None

with st.spinner("Fetching data..."):
    try:
        servers, checks, shifts, reservations = load_data(
            selected_date.strftime("%Y-%m-%d"),
            mode_override,
            env_label(),
            IS_STANDALONE,
            sim_time_iso,
        )
    except Exception as e:
        st.error(f"Pipeline error: {e}")
        st.stop()


# ---------------------------------------------------------------------------
# Top-level metrics
# ---------------------------------------------------------------------------

st.divider()
m1, m2, m3, m4, m5, m6 = st.columns(6)

closed   = [c for c in checks if c.closed_at]
open_    = [c for c in checks if not c.closed_at]
no_shows = [r for r in reservations if r.status.value == "no_show"]
vips     = [r for r in reservations if r.is_vip]
upcoming = [r for r in reservations if r.status.value == "booked"]
seated   = [r for r in reservations if r.status.value == "seated"]

avg_turn = (
    sum(c.turn_time_minutes for c in closed) / len(closed) if closed else 0
)
avg_tip = (
    sum(c.tip_percentage for c in closed if c.tip_percentage) /
    max(len([c for c in closed if c.tip_percentage]), 1)
    if closed else 0
)

m1.metric("Servers On Floor", len(shifts))
m2.metric("Checks Closed",    len(closed))
m3.metric("Checks Open",      len(open_))
m4.metric("Reservations",     len(reservations))
m5.metric("Avg Turn Time",    f"{avg_turn:.0f} min")
m6.metric("Avg Tip",          f"{avg_tip:.1f}%")


# ---------------------------------------------------------------------------
# Section 1: Reservation Timeline
# ---------------------------------------------------------------------------

st.divider()
st.subheader("Reservation Timeline")

if reservations:
    res_rows = []
    for r in reservations:
        res_rows.append({
            "Time":       r.scheduled_at.strftime("%I:%M %p"),
            "Guest":      r.guest_name,
            "Party":      r.party_size,
            "Status":     r.status.value.replace("_", " ").title(),
            "VIP":        "★" if r.is_vip else "",
            "Wait (min)": f"{r.wait_minutes:.0f}" if r.wait_minutes is not None else "—",
            "Notes":      r.notes or "",
        })
    df_res = pd.DataFrame(res_rows)

    status_counts = df_res["Status"].value_counts()
    scol1, scol2, scol3, scol4 = st.columns(4)
    scol1.metric("Upcoming",  status_counts.get("Booked", 0))
    scol2.metric("Seated",    status_counts.get("Seated", 0))
    scol3.metric("Completed", status_counts.get("Completed", 0))
    scol4.metric("No-shows",  status_counts.get("No Show", 0))

    st.dataframe(
        df_res,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Party": st.column_config.NumberColumn(width="small"),
            "VIP":   st.column_config.TextColumn(width="small"),
        },
    )
else:
    st.info("No reservations for this date.")


# ---------------------------------------------------------------------------
# Section 2: Server Performance Breakdown
# ---------------------------------------------------------------------------

st.divider()
st.subheader("Server Performance")

if closed:
    server_map = {s.provider_id: s.name for s in servers}
    per_server: dict[str, list] = {}
    for c in closed:
        per_server.setdefault(c.server_id, []).append(c)

    srv_rows = []
    for sid, srv_checks in per_server.items():
        turns     = [c.turn_time_minutes for c in srv_checks]
        tips      = [c.tip_percentage for c in srv_checks if c.tip_percentage]
        rev_cover = [c.revenue_per_cover for c in srv_checks if c.revenue_per_cover]
        srv_rows.append({
            "Server":         server_map.get(sid, sid),
            "Tables":         len(srv_checks),
            "Covers":         sum(c.covers for c in srv_checks),
            "Avg Turn (min)": round(sum(turns) / len(turns), 1),
            "Avg Tip %":      round(sum(tips) / len(tips), 1) if tips else 0,
            "Rev / Cover":    f"${sum(rev_cover)/len(rev_cover):.2f}" if rev_cover else "—",
        })

    df_srv = pd.DataFrame(srv_rows).sort_values("Tables", ascending=False)

    st.dataframe(df_srv, use_container_width=True, hide_index=True)

    # Visual: covers per server
    st.bar_chart(
        df_srv.set_index("Server")["Covers"],
        use_container_width=True,
        height=220,
    )
else:
    st.info("No closed checks yet for this service period.")


# ---------------------------------------------------------------------------
# Section 3: Shift Overview
# ---------------------------------------------------------------------------

st.divider()
st.subheader("Shift Overview")

if shifts:
    server_map = {s.provider_id: s.name for s in servers}
    shift_rows = []
    for sh in shifts:
        shift_rows.append({
            "Server":    server_map.get(sh.server_id, sh.server_id),
            "Clock In":  sh.clock_in.strftime("%I:%M %p"),
            "Clock Out": sh.clock_out.strftime("%I:%M %p") if sh.clock_out else "On floor",
            "Status":    "Active" if not sh.clock_out else "Clocked out",
        })
    df_shifts = pd.DataFrame(shift_rows)
    st.dataframe(df_shifts, use_container_width=True, hide_index=True)
else:
    st.info("No shifts found.")


# ---------------------------------------------------------------------------
# Section 4: Scoring Engine — Server Profiles & Seating Recommendations
# ---------------------------------------------------------------------------

st.divider()
st.subheader("Scoring Engine")

from foh.scoring.engine import build_profiles, recommend, DEFAULT_WEIGHTS

profiles = build_profiles(servers, checks, shifts)

if profiles:
    # --- Server score cards ---
    st.markdown("**Server Performance Scores** *(normalized within active pool)*")

    profiles_sorted = sorted(profiles, key=lambda p: p.performance_score, reverse=True)
    server_map = {s.provider_id: s.name for s in servers}

    score_rows = []
    for p in profiles_sorted:
        score_rows.append({
            "Server":       p.server.name,
            "Score":        p.performance_score,
            "Tables Done":  p.check_count,
            "Open Tables":  p.open_tables,
            "Open Covers":  p.open_covers,
            "Avg Tip %":    round(p.avg_tip_pct, 1),
            "Avg Turn":     f"{p.avg_turn_minutes:.0f} min" if p.avg_turn_minutes else "—",
            "Rev/Cover":    f"${p.avg_revenue_cover:.2f}" if p.avg_revenue_cover else "—",
        })
    df_scores = pd.DataFrame(score_rows)

    st.dataframe(
        df_scores,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Score": st.column_config.ProgressColumn(
                "Score",
                help="Composite performance score (0–1)",
                min_value=0.0,
                max_value=1.0,
                format="%.2f",
            ),
        },
    )

    # --- Seating recommendations for upcoming parties ---
    st.markdown("**Seating Recommendations** *(next parties in queue)*")

    upcoming_res = [r for r in reservations if r.status.value == "booked"]

    if upcoming_res:
        # Show recommendations for the next 5 upcoming reservations
        for res in upcoming_res[:5]:
            suggestions = recommend(res, profiles, top_n=3)
            vip_badge = " ★ VIP" if res.is_vip else ""
            with st.container():
                st.markdown(
                    f"**{res.guest_name}** · Party of {res.party_size}"
                    f" · {res.scheduled_at.strftime('%I:%M %p')}{vip_badge}"
                )
                if res.notes:
                    st.caption(f"Note: {res.notes}")
                rec_cols = st.columns(min(len(suggestions), 3))
                for col, sug in zip(rec_cols, suggestions):
                    with col:
                        medal = ["🥇", "🥈", "🥉"][sug.rank - 1]
                        st.metric(
                            label=f"{medal} {sug.server.name}",
                            value=f"{sug.match_score:.0%}",
                        )
                        for line in sug.reasoning:
                            st.caption(f"• {line}")
                st.divider()
    else:
        st.info("No upcoming reservations to recommend for.")

    # --- Floor snapshot — open tables right now ---
    open_checks = [c for c in checks if not c.closed_at]
    if open_checks:
        st.markdown("**Floor Snapshot** *(currently open tables)*")
        floor_rows = []
        server_map_pid = {s.provider_id: s.name for s in servers}
        for c in open_checks:
            elapsed = (
                int(((sim_time or datetime.now(timezone.utc)) - c.opened_at).total_seconds() / 60)
                if c.opened_at else "—"
            )
            floor_rows.append({
                "Server":        server_map_pid.get(c.server_id, c.server_id),
                "Table":         c.table_id or "—",
                "Covers":        c.covers,
                "Open (min)":    elapsed,
                "Subtotal":      f"${float(c.subtotal):.2f}" if c.subtotal else "—",
            })
        df_floor = pd.DataFrame(floor_rows).sort_values("Server")
        st.dataframe(df_floor, use_container_width=True, hide_index=True)
else:
    st.info("Not enough shift/check data to build server profiles yet.")


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.divider()
time_label = (
    f"Simulated {sim_label_hour}:{sim_min:02d} {sim_label_ampm}"
    if sim_time else datetime.now().strftime("%I:%M:%S %p")
)
st.caption(
    f"Data at {time_label} · "
    f"Servers: {len(servers)} · "
    f"Mock servers: Toast :8001 · OpenTable :8002"
)
