"""
FOH Intel — pipeline entry point.
Reads APP_ENV from .env to select development (mock), sandbox, or production providers.
"""
import asyncio
from datetime import datetime
from foh.providers.factory import get_pos_provider, get_reservation_provider, env_label
from foh.scoring.engine import build_profiles, recommend, DEFAULT_WEIGHTS
from foh.config import settings


async def main():
    date = datetime.today()
    print(f"\n=== FOH Intel [{env_label()}] — {date.strftime('%A %b %d, %Y')} ===\n")

    # --- Fetch data ---
    pos = get_pos_provider()
    await pos.authenticate()
    servers      = await pos.get_servers()
    checks       = await pos.get_checks(date)
    shifts       = await pos.get_shifts(date)

    res          = get_reservation_provider()
    await res.authenticate()
    reservations = await res.get_reservations(date)

    # --- Build server profiles ---
    profiles = build_profiles(servers, checks, shifts, DEFAULT_WEIGHTS)

    closed   = [c for c in checks if c.closed_at]
    open_    = [c for c in checks if not c.closed_at]
    upcoming = [r for r in reservations if r.status.value == "booked"]

    print(f"POS  |  Servers on floor: {len(profiles)}  "
          f"Checks closed: {len(closed)}  Open: {len(open_)}")

    # --- Server performance summary ---
    if profiles:
        print("\n  Server scores (performance · load · checks · covers):")
        for p in sorted(profiles, key=lambda x: -x.performance_score):
            bar = "█" * int(p.performance_score * 10) + "░" * (10 - int(p.performance_score * 10))
            load = f"{p.open_tables} open" if p.open_tables else "available"
            print(f"    {p.server.name:<18} [{bar}] {p.performance_score:.0%}  "
                  f"{load:<12}  {p.check_count} checks  {p.total_covers} covers")

    # --- Seating recommendations ---
    pending   = [r for r in reservations if r.status.value == "booked"]
    completed = [r for r in reservations if r.status.value == "completed"]

    if not profiles:
        print("\nNo servers on floor yet.")
        return

    if pending:
        # Live mode — recommend for upcoming parties
        print(f"\nRES  |  Upcoming: {len(pending)}  —  Seating recommendations:\n")
        sample = pending[:5]
    elif completed:
        # Batch mode — retrospective analysis for tuning
        print(f"\nRES  |  {len(completed)} completed · Retrospective recommendations (batch):\n")
        sample = completed[:5]
    else:
        print(f"\nRES  |  {len(reservations)} reservations loaded.")
        return

    for res_item in sample:
        vip_tag = " [VIP]" if res_item.is_vip else ""
        print(f"  {res_item.scheduled_at.strftime('%I:%M %p')}  "
              f"{res_item.guest_name:<22} party of {res_item.party_size}{vip_tag}")
        suggestions = recommend(res_item, profiles, DEFAULT_WEIGHTS, top_n=3)
        for s in suggestions:
            reasons = " · ".join(s.reasoning) if s.reasoning else "—"
            print(f"    #{s.rank} {s.server.name:<18} {s.match_score:.0%}  {reasons}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
