"""
FOH Intel — Floor Activity
Real-time per-server item feed: drinks → appetizers → entrees → desserts.
Tracks upsell rate, item send times, table open/close events, and section load.
This is the data layer that will feed ML training on changing floor metrics.
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timezone, timedelta
from collections import defaultdict

from foh.dashboard_utils import (
    init_session_state, render_sim_sidebar, is_standalone,
    load_floor_data, get_sim_time, sim_time_label, maybe_advance_sim,
)

st.set_page_config(page_title="Floor Activity | FOH Intel", layout="wide", page_icon="🍴")
init_session_state()
render_sim_sidebar("Floor Activity")

date_str   = st.session_state["sim_date"].strftime("%Y-%m-%d")
mode       = st.session_state["data_mode"]
sim_time   = get_sim_time()
sim_iso    = sim_time.isoformat() if sim_time else None
standalone = is_standalone()
now        = sim_time or datetime.now(timezone.utc)

st.title("Floor Activity")
if sim_time:
    st.caption(f"Simulating **{sim_time_label()}** — item feed updates as sim advances")
else:
    st.caption(f"Live · {now.strftime('%I:%M:%S %p')}")

with st.spinner("Loading floor data…"):
    try:
        servers, checks, shifts, reservations = load_floor_data(
            date_str, mode, sim_iso, standalone
        )
    except Exception as e:
        st.error(f"Pipeline error: {e}")
        st.stop()

server_map = {s.provider_id: s.name for s in servers}

# ---------------------------------------------------------------------------
# Helper: checks that were "newly opened" (within last 15 sim-minutes)
# ---------------------------------------------------------------------------

NEW_TABLE_WINDOW = timedelta(minutes=15)
open_checks  = [c for c in checks if not c.closed_at]
new_tables   = [c for c in open_checks if (now - c.opened_at) <= NEW_TABLE_WINDOW]

if new_tables:
    for c in new_tables:
        server_name = server_map.get(c.server_id, c.server_id)
        age_min = int((now - c.opened_at).total_seconds() / 60)
        st.success(
            f"🆕 New table opened — **{server_name}** · Table {c.table_id} · "
            f"{c.covers} covers · {age_min} min ago"
        )

# ---------------------------------------------------------------------------
# Top-level upsell & category metrics
# ---------------------------------------------------------------------------

all_items = [it for c in checks for it in c.items]
upsell_items = [it for it in all_items if it.is_upsell]

by_cat = defaultdict(int)
for it in all_items:
    by_cat[it.category] += it.quantity

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Items Fired",    len(all_items))
m2.metric("Upsells",        len(upsell_items))
m3.metric("Upsell Rate",    f"{len(upsell_items)/max(len(all_items),1)*100:.0f}%")
m4.metric("Tables w/ Dessert",
          len(set(c.provider_id for c in checks for it in c.items if it.category == "dessert")))
m5.metric("Bottles of Wine",
          sum(it.quantity for it in all_items if it.name == "Bottle of Wine"))

# ---------------------------------------------------------------------------
# Per-server upsell leaderboard
# ---------------------------------------------------------------------------

st.divider()
st.subheader("Upsell Leaderboard")

upsell_rows = []
for srv in servers:
    srv_checks = [c for c in checks if c.server_id == srv.provider_id]
    srv_items  = [it for c in srv_checks for it in c.items]
    srv_upsell = [it for it in srv_items if it.is_upsell]
    if not srv_items:
        continue
    upsell_rows.append({
        "Server":       srv.name,
        "Items Fired":  len(srv_items),
        "Upsells":      len(srv_upsell),
        "Upsell Rate":  len(srv_upsell) / len(srv_items),
        "Desserts Sold": sum(1 for it in srv_items if it.category == "dessert"),
        "Bottles Wine":  sum(it.quantity for it in srv_items if it.name == "Bottle of Wine"),
        "Premium Cocktails": sum(it.quantity for it in srv_items if it.name == "Craft Cocktail"),
    })

if upsell_rows:
    upsell_rows.sort(key=lambda x: x["Upsell Rate"], reverse=True)
    st.dataframe(
        pd.DataFrame(upsell_rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Upsell Rate": st.column_config.ProgressColumn(
                "Upsell Rate", min_value=0.0, max_value=1.0, format="%.0%"
            ),
        },
    )

# ---------------------------------------------------------------------------
# Category breakdown — what's been ordered across the floor
# ---------------------------------------------------------------------------

st.divider()
st.subheader("Category Breakdown")

cat_order = ["drink", "appetizer", "entree", "dessert"]
cc1, cc2, cc3, cc4 = st.columns(4)
cat_cols = {"drink": cc1, "appetizer": cc2, "entree": cc3, "dessert": cc4}
cat_labels = {"drink": "🍷 Drinks", "appetizer": "🥗 Apps", "entree": "🍽 Entrees", "dessert": "🍮 Desserts"}

for cat in cat_order:
    cat_items = [it for it in all_items if it.category == cat]
    item_counts: dict[str, int] = defaultdict(int)
    for it in cat_items:
        item_counts[it.name] += it.quantity
    with cat_cols[cat]:
        st.markdown(f"**{cat_labels[cat]}** ({sum(item_counts.values())})")
        for name, qty in sorted(item_counts.items(), key=lambda x: -x[1]):
            upsell_flag = " ⬆" if any(i.is_upsell and i.name == name for i in cat_items) else ""
            st.caption(f"{name}{upsell_flag}: {qty}")

# ---------------------------------------------------------------------------
# Per-server section view — expandable cards
# ---------------------------------------------------------------------------

st.divider()
st.subheader("Section View")

# Group checks by server
by_server: dict[str, list] = defaultdict(list)
for c in checks:
    by_server[c.server_id].append(c)

# Sort servers by number of active tables (descending)
server_order = sorted(
    by_server.keys(),
    key=lambda sid: len([c for c in by_server[sid] if not c.closed_at]),
    reverse=True,
)

for sid in server_order:
    srv_name    = server_map.get(sid, sid)
    srv_checks  = by_server[sid]
    active_chks = [c for c in srv_checks if not c.closed_at]
    closed_chks = [c for c in srv_checks if c.closed_at]

    # Shift status
    on_shift = any(sh.server_id == sid and sh.clock_out is None for sh in shifts)
    status_icon = "🟢" if on_shift else "⚫"

    with st.expander(
        f"{status_icon} **{srv_name}** — {len(active_chks)} open · {len(closed_chks)} closed",
        expanded=(len(active_chks) > 0),
    ):
        if active_chks:
            st.markdown("**Open Tables**")
            for chk in sorted(active_chks, key=lambda c: c.opened_at):
                elapsed = int((now - chk.opened_at).total_seconds() / 60)
                items_so_far = chk.items
                upsells_here = [it for it in items_so_far if it.is_upsell]

                tcol1, tcol2 = st.columns([1, 3])
                with tcol1:
                    st.markdown(f"**{chk.table_id}**")
                    st.caption(f"{chk.covers} covers · {elapsed} min")
                    st.caption(f"${float(chk.subtotal):.2f} running")
                with tcol2:
                    if items_so_far:
                        # Show item timeline
                        for it in sorted(items_so_far, key=lambda i: i.sent_at):
                            mins_in = int((it.sent_at - chk.opened_at).total_seconds() / 60)
                            upsell_tag = " ⬆" if it.is_upsell else ""
                            cat_icon = {
                                "drink": "🍷", "appetizer": "🥗",
                                "entree": "🍽", "dessert": "🍮",
                            }.get(it.category, "•")
                            st.caption(
                                f"+{mins_in:02d}m {cat_icon} {it.name}{upsell_tag}"
                            )
                    else:
                        st.caption("No items fired yet")

                if upsells_here:
                    st.caption(
                        f"✓ {len(upsells_here)} upsell(s): "
                        + ", ".join(set(it.name for it in upsells_here))
                    )
                st.divider()

        if closed_chks:
            st.markdown("**Closed Tables**")
            closed_rows = []
            for chk in sorted(closed_chks, key=lambda c: c.closed_at, reverse=True):
                chk_items   = chk.items
                upsell_cnt  = sum(1 for it in chk_items if it.is_upsell)
                total_items = len(chk_items)
                closed_rows.append({
                    "Table":     chk.table_id,
                    "Covers":    chk.covers,
                    "Turn (min)": int(chk.turn_time_minutes) if chk.turn_time_minutes else "—",
                    "Subtotal":  f"${float(chk.subtotal):.2f}",
                    "Tip %":     f"{chk.tip_percentage:.1f}%" if chk.tip_percentage else "—",
                    "Items":     total_items,
                    "Upsells":   upsell_cnt,
                })
            st.dataframe(
                pd.DataFrame(closed_rows),
                use_container_width=True,
                hide_index=True,
                column_config={"Covers": st.column_config.NumberColumn(width="small")},
            )

        if not srv_checks:
            st.caption("No tables assigned yet this service.")

# ---------------------------------------------------------------------------
# Item fire log — chronological feed across all servers
# ---------------------------------------------------------------------------

st.divider()
st.subheader("Item Fire Log")

fire_rows = []
for c in sorted(checks, key=lambda x: x.opened_at):
    srv_name = server_map.get(c.server_id, c.server_id)
    for it in sorted(c.items, key=lambda i: i.sent_at):
        mins_in = int((it.sent_at - c.opened_at).total_seconds() / 60)
        fire_rows.append({
            "Sent At":   it.sent_at.strftime("%I:%M %p"),
            "Server":    srv_name,
            "Table":     c.table_id,
            "Item":      it.name,
            "Category":  it.category.title(),
            "Price":     f"${float(it.price):.2f}",
            "Upsell":    "⬆" if it.is_upsell else "",
            "Min In":    mins_in,
        })

if fire_rows:
    fire_rows.sort(key=lambda x: x["Sent At"])
    df_fire = pd.DataFrame(fire_rows)
    st.dataframe(
        df_fire,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Upsell":  st.column_config.TextColumn(width="small"),
            "Min In":  st.column_config.NumberColumn(width="small"),
        },
    )
else:
    st.info("No items fired yet — advance the simulation to see the floor come alive.")

maybe_advance_sim()
