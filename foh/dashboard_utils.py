"""
Shared utilities for all FOH Intel dashboard pages.

Provides:
  - Session-state initialization and sim controls
  - Sidebar simulator (date, mode, time scrubber, play/pause/speed)
  - Cached floor data loader (standalone + HTTP paths)
  - Helper: get_sim_time(), sim_time_label(), maybe_advance_sim()
"""
from __future__ import annotations

import os
import socket
import time as _time
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import streamlit as st

# ---------------------------------------------------------------------------
# Simulation constants
# ---------------------------------------------------------------------------

SERVICE_START_HOUR = 17        # 5:00 PM
SERVICE_END_HOUR   = 23        # 11:00 PM
STEP_MINUTES       = 15
TOTAL_STEPS        = (SERVICE_END_HOUR - SERVICE_START_HOUR) * 60 // STEP_MINUTES  # 24


# ---------------------------------------------------------------------------
# Standalone detection (cached per session)
# ---------------------------------------------------------------------------

def is_standalone() -> bool:
    if "foh_standalone" not in st.session_state:
        from foh.config import settings
        result = (
            os.getenv("STANDALONE", "false").lower() == "true"
            or settings.standalone
        )
        if not result:
            for port in (settings.toast_mock_port, settings.opentable_mock_port):
                try:
                    with socket.create_connection(("localhost", port), timeout=1):
                        pass
                except OSError:
                    result = True
                    break
        st.session_state["foh_standalone"] = result
    return st.session_state["foh_standalone"]


# ---------------------------------------------------------------------------
# Session-state bootstrap
# ---------------------------------------------------------------------------

def init_session_state() -> None:
    defaults: dict = {
        "sim_active":  False,
        "sim_step":    TOTAL_STEPS // 3,   # default ~ 7 PM
        "sim_running": False,
        "sim_speed":   1.0,
        "sim_date":    datetime.today().date(),
        "data_mode":   "live",
        "score_history": {},               # step -> {server_id: score}
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ---------------------------------------------------------------------------
# Sim time helpers
# ---------------------------------------------------------------------------

def get_sim_time() -> datetime | None:
    """Return the current sim datetime or None if using real time."""
    if not st.session_state.get("sim_active"):
        return None
    d = st.session_state["sim_date"]
    offset_min = st.session_state["sim_step"] * STEP_MINUTES
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc) + timedelta(
        hours=SERVICE_START_HOUR, minutes=offset_min
    )


def sim_time_label() -> str:
    step = st.session_state.get("sim_step", 0)
    offset_min = step * STEP_MINUTES
    h = SERVICE_START_HOUR + offset_min // 60
    m = offset_min % 60
    label_h = h if h <= 12 else h - 12
    ampm = "PM" if 12 <= h < 24 else "AM"
    return f"{label_h}:{m:02d} {ampm}"


def maybe_advance_sim() -> None:
    """
    Call at the bottom of any page that should auto-advance the sim.
    When running, sleeps briefly then increments step and reruns.
    """
    if st.session_state.get("sim_running") and st.session_state.get("sim_active"):
        if st.session_state["sim_step"] < TOTAL_STEPS:
            _time.sleep(1.0 / max(0.25, st.session_state.get("sim_speed", 1.0)))
            st.session_state["sim_step"] += 1
            st.rerun()
        else:
            st.session_state["sim_running"] = False


# ---------------------------------------------------------------------------
# Sidebar simulator controls
# ---------------------------------------------------------------------------

def render_sim_sidebar(page_title: str = "FOH Intel") -> None:
    """
    Renders the full simulator sidebar.
    All state is written directly to st.session_state.
    Call init_session_state() before this.
    """
    with st.sidebar:
        st.markdown(f"## {page_title}")
        st.markdown("---")

        # Date
        date_val = st.date_input(
            "Service Date",
            value=st.session_state["sim_date"],
            key="_sidebar_date",
        )
        st.session_state["sim_date"] = date_val

        # Data mode
        mode_idx = 0 if st.session_state["data_mode"] == "live" else 1
        data_mode = st.selectbox(
            "Data Mode", ["live", "batch"],
            index=mode_idx, key="_sidebar_mode",
        )
        st.session_state["data_mode"] = data_mode
        os.environ["DATA_MODE"] = data_mode

        st.markdown("---")
        st.markdown("**Time Simulator**")

        sim_active = st.toggle(
            "Enable Simulation",
            value=st.session_state["sim_active"],
            key="_sidebar_sim_active",
            help="Freeze the floor at a specific point in service",
        )
        st.session_state["sim_active"] = sim_active

        if sim_active:
            step = st.slider(
                "Service Time",
                min_value=0, max_value=TOTAL_STEPS,
                value=st.session_state["sim_step"],
                key="_sidebar_step",
                help="5 PM → 11 PM in 15-minute steps",
            )
            st.session_state["sim_step"] = step
            st.caption(f"Simulating: **{sim_time_label()}**")

            # Play / Pause / Reset
            c1, c2 = st.columns(2)
            with c1:
                lbl = "⏸ Pause" if st.session_state["sim_running"] else "▶ Play"
                if st.button(lbl, use_container_width=True, key="_btn_play"):
                    st.session_state["sim_running"] = not st.session_state["sim_running"]
                    if st.session_state["sim_running"] and step >= TOTAL_STEPS:
                        st.session_state["sim_step"] = 0
            with c2:
                if st.button("⏮ Reset", use_container_width=True, key="_btn_reset"):
                    st.session_state["sim_step"] = 0
                    st.session_state["sim_running"] = False
                    st.session_state["score_history"] = {}

            speed = st.select_slider(
                "Playback Speed",
                options=[0.25, 0.5, 1.0, 2.0, 4.0],
                value=st.session_state.get("sim_speed", 1.0),
                key="_sidebar_speed",
                format_func=lambda x: f"{x}×",
            )
            st.session_state["sim_speed"] = speed

        else:
            st.caption("Using real time")

        st.markdown("---")
        standalone = is_standalone()
        mode_note = "standalone" if standalone else "HTTP providers"
        st.caption(f"Mode: {mode_note}")


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@st.cache_data(ttl=15, show_spinner=False)
def load_floor_data(
    date_str: str,
    mode: str,
    sim_time_iso: str | None,
    standalone: bool,
):
    """
    Primary data loader. Cached 15 s.
    sim_time_iso is an ISO string (or None) for cache-key stability.
    """
    if standalone:
        return _standalone_load(date_str, mode, sim_time_iso)

    import asyncio
    from foh.providers.factory import get_pos_provider, get_reservation_provider

    date = datetime.strptime(date_str, "%Y-%m-%d")

    async def _fetch():
        pos = get_pos_provider()
        await pos.authenticate()
        servers = await pos.get_servers()
        checks  = await pos.get_checks(date)
        shifts  = await pos.get_shifts(date)
        res     = get_reservation_provider()
        await res.authenticate()
        reservations = await res.get_reservations(date)
        return servers, checks, shifts, reservations

    return asyncio.run(_fetch())


def _standalone_load(date_str: str, mode: str, sim_time_iso: str | None):
    from mock_servers.toast.data import generate_employees, generate_shifts, generate_orders
    from mock_servers.opentable.data import generate_reservations
    from foh.models.pos import Server, Check, OrderItem, Shift, OrderStatus
    from foh.models.reservations import Reservation, ReservationStatus, DiningPreference

    sim_time = datetime.fromisoformat(sim_time_iso) if sim_time_iso else None
    date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    # Servers
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
            clock_out=(
                datetime.fromisoformat(s["outDate"].replace("Z", "+00:00"))
                if s.get("outDate") else None
            ),
        )
        for s in raw_shifts
    ]

    # Orders → Checks + items
    start = date
    end   = date.replace(hour=23, minute=59, second=59)
    raw_orders = generate_orders(start, end, mode, sim_time=sim_time)
    now_cutoff = sim_time or datetime.now(timezone.utc)
    checks: list[Check] = []
    for order in raw_orders:
        for chk in order.get("checks", []):
            payments = chk.get("payments", [])
            tip = sum(Decimal(str(p.get("tipAmount", 0))) for p in payments)

            # Only include items that have been fired by sim_time
            items: list[OrderItem] = []
            for it in chk.get("items", []):
                sent = datetime.fromisoformat(it["sentAt"].replace("Z", "+00:00"))
                if sent <= now_cutoff:
                    items.append(OrderItem(
                        name=it["name"],
                        category=it["category"],
                        quantity=it["quantity"],
                        price=Decimal(str(it["unitPrice"])),
                        sent_at=sent,
                        is_upsell=it.get("isUpsell", False),
                    ))

            checks.append(Check(
                provider_id=chk["guid"],
                server_id=order["server"]["guid"],
                table_id=order["table"]["guid"],
                opened_at=datetime.fromisoformat(order["openedDate"].replace("Z", "+00:00")),
                closed_at=(
                    datetime.fromisoformat(order["closedDate"].replace("Z", "+00:00"))
                    if order.get("closedDate") else None
                ),
                covers=order.get("numberOfGuests", 0),
                subtotal=Decimal(str(chk.get("amount", 0))),
                tax=Decimal(str(chk.get("taxAmount", 0))),
                tip=tip if tip > 0 else None,
                status=OrderStatus.CLOSED if order.get("closedDate") else OrderStatus.OPEN,
                items=items,
            ))

    # Reservations
    PREF_MAP = {
        "window":               DiningPreference.WINDOW,
        "booth":                DiningPreference.BOOTH,
        "bar":                  DiningPreference.BAR,
        "patio":                DiningPreference.PATIO,
        "quiet section":        DiningPreference.QUIET,
        "high chair":           DiningPreference.HIGH_CHAIR,
        "wheelchair accessible": DiningPreference.ACCESSIBLE,
    }
    STATUS_MAP = {
        "booked":    ReservationStatus.BOOKED,
        "seated":    ReservationStatus.SEATED,
        "completed": ReservationStatus.COMPLETED,
        "no_show":   ReservationStatus.NO_SHOW,
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
