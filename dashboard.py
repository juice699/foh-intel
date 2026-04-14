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
from datetime import datetime, timezone
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
# Data loading — two paths: standalone (in-process) or HTTP providers
# ---------------------------------------------------------------------------

def _standalone_load(date_str: str, mode: str):
    """
    Generate data entirely in-process using the mock data generators.
    No HTTP servers required — safe for Streamlit Community Cloud.
    """
    from mock_servers.toast.data import (
        generate_employees, generate_shifts, generate_orders, EMPLOYEES
    )
    from mock_servers.opentable.data import generate_reservations, generate_guest
    from foh.models.pos import Server, Check, Shift, OrderStatus, PaymentMethod
    from foh.models.reservations import Reservation, ReservationStatus, DiningPreference, Guest
    from decimal import Decimal

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
    raw_shifts = generate_shifts(date, mode)
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
    from datetime import timedelta
    start = date
    end   = date.replace(hour=23, minute=59, second=59)
    raw_orders = generate_orders(start, end, mode)
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
    raw_res = generate_reservations(date, mode)
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
def load_data(date_str: str, mode: str, env: str, standalone: bool):
    """Cached 15s — auto-refreshes in live mode to reflect floor changes."""
    if standalone:
        return _standalone_load(date_str, mode)

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


with st.spinner("Fetching data..."):
    try:
        servers, checks, shifts, reservations = load_data(
            selected_date.strftime("%Y-%m-%d"),
            mode_override,
            env_label(),
            IS_STANDALONE,
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
            "Server":   server_map.get(sh.server_id, sh.server_id),
            "Clock In":  sh.clock_in.strftime("%I:%M %p"),
            "Clock Out": sh.clock_out.strftime("%I:%M %p") if sh.clock_out else "On floor",
            "Status":   "Active" if not sh.clock_out else "Clocked out",
        })
    df_shifts = pd.DataFrame(shift_rows)
    st.dataframe(df_shifts, use_container_width=True, hide_index=True)
else:
    st.info("No shifts found.")


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.divider()
st.caption(
    f"Data pulled at {datetime.now().strftime('%I:%M:%S %p')} · "
    f"Servers: {len(servers)} · "
    f"Mock servers: Toast :8001 · OpenTable :8002"
)
