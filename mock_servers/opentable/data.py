"""
OpenTable mock data generator.

Guest profiles are stable (seeded by guest ID).
Reservations are seeded by date:
  - batch mode: all reservations completed or no-showed
  - live mode:  upcoming reservations are still booked; active are seated;
                earlier ones are completed or no-showed
"""
import random
from datetime import datetime, timezone, timedelta


# ---------------------------------------------------------------------------
# Stable guest pool
# ---------------------------------------------------------------------------

_FIRST = ["James", "Maria", "Chen", "Sophia", "Marcus", "Elena",
          "David", "Priya", "Jordan", "Naomi", "Carlos", "Ingrid"]
_LAST  = ["Smith", "Santos", "Williams", "Brown", "Taylor",
          "Anderson", "Lee", "Patel", "Hayes", "Okafor", "Reyes", "Müller"]

_PREFS = ["window", "booth", "bar", "patio", "quiet section",
          "high chair", "wheelchair accessible"]

_NOTES = [
    "Anniversary dinner",
    "Birthday celebration — please do not sing",
    "Business dinner, quiet table preferred",
    "Regular — loves the corner booth",
    "Severe nut allergy — notify kitchen",
    "Celebrating promotion",
    None, None, None, None,
]


def _guest_rng(guest_id: str) -> random.Random:
    index = int(guest_id.split("-")[-1]) if guest_id.split("-")[-1].isdigit() else 0
    return random.Random(index + 9999)


def generate_guest(guest_id: str) -> dict:
    rng = _guest_rng(guest_id)
    first = rng.choice(_FIRST)
    last  = rng.choice(_LAST)
    index = guest_id.split("-")[-1]
    return {
        "id":                guest_id,
        "firstName":         first,
        "lastName":          last,
        "email":             f"{first.lower()}.{last.lower()}{index}@example.com",
        "phone":             f"555-{rng.randint(1000,9999)}",
        "visitCount":        rng.randint(0, 30),
        "notes":             rng.choice(_NOTES),
        "diningPreferences": rng.sample(_PREFS, k=rng.randint(0, 2)),
    }


# ---------------------------------------------------------------------------
# Reservation generator
# ---------------------------------------------------------------------------

def _service_anchor(date: datetime) -> datetime:
    """Dinner service starts 5:00 PM UTC on the given date."""
    return date.replace(hour=17, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)


def generate_reservations(date: datetime, mode: str) -> list[dict]:
    rng  = random.Random(date.toordinal() + 7)
    now  = datetime.now(timezone.utc)
    svc  = _service_anchor(date)
    is_today = date.date() == now.date()

    num = rng.randint(18, 34)
    reservations = []

    for i in range(num):
        guest_id = f"guest-{(date.toordinal() * 100 + i):07d}"
        guest    = generate_guest(guest_id)

        offset      = timedelta(minutes=rng.randint(0, 240))
        scheduled   = svc + offset
        party_size  = rng.choices([2, 3, 4, 5, 6, 8], weights=[35, 12, 28, 10, 10, 5])[0]
        prefs       = rng.sample(_PREFS, k=rng.randint(0, 2))
        is_vip      = rng.random() < 0.08
        notes       = rng.choice(_NOTES)

        # Determine status
        if mode == "live" and is_today:
            if scheduled > now + timedelta(minutes=30):
                status    = "booked"
                seated_at = None
                table_id  = None
                server_id = None
            elif scheduled > now - timedelta(minutes=90):
                status    = "seated"
                wait      = rng.randint(-5, 18)
                seated_at = scheduled + timedelta(minutes=wait)
                table_id  = f"tbl-{rng.randint(1, 20):04d}"
                server_id = f"emp-{rng.randint(1, 8):04d}"
            else:
                status    = rng.choices(["completed", "no_show"], weights=[88, 12])[0]
                wait      = rng.randint(-5, 18)
                seated_at = scheduled + timedelta(minutes=wait) if status == "completed" else None
                table_id  = f"tbl-{rng.randint(1, 20):04d}" if status == "completed" else None
                server_id = f"emp-{rng.randint(1, 8):04d}" if status == "completed" else None
        else:
            # Batch — everything resolved
            status    = rng.choices(["completed", "no_show"], weights=[88, 12])[0]
            wait      = rng.randint(-5, 18)
            seated_at = scheduled + timedelta(minutes=wait) if status == "completed" else None
            table_id  = f"tbl-{rng.randint(1, 20):04d}" if status == "completed" else None
            server_id = f"emp-{rng.randint(1, 8):04d}" if status == "completed" else None

        reservations.append({
            "id":              f"res-{date.strftime('%Y%m%d')}-{i:03d}",
            "guestId":         guest_id,
            "guestName":       f"{guest['firstName']} {guest['lastName']}",
            "partySize":       party_size,
            "dateTime":        scheduled.isoformat(),
            "seatedAt":        seated_at.isoformat() if seated_at else None,
            "status":          status,
            "tableId":         table_id,
            "serverId":        server_id,
            "notes":           notes,
            "specialRequests": prefs,
            "isVip":           is_vip,
        })

    return sorted(reservations, key=lambda r: r["dateTime"])
