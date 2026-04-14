"""
Toast mock data generator.

Fixtures (employees, tables, jobs) are stable across all dates — same GUIDs always.
Service data (orders, shifts) is seeded by date for determinism:
  - batch mode: full closed service, all checks settled, all shifts clocked out
  - live mode:  anchored to datetime.now(); open checks and active shifts exist
"""
import random
from datetime import datetime, timezone, timedelta


# ---------------------------------------------------------------------------
# Stable restaurant fixtures
# ---------------------------------------------------------------------------

JOB_GUID = "job-0001-server"

# ---------------------------------------------------------------------------
# Menu — stable item catalog
# ---------------------------------------------------------------------------

MENU_ITEMS = [
    # Drinks
    {"id": "MI-K01", "name": "Sparkling Water",     "category": "drink",     "price": 6.00,  "upsell": False},
    {"id": "MI-K02", "name": "House Wine Glass",     "category": "drink",     "price": 12.00, "upsell": False},
    {"id": "MI-K03", "name": "Craft Cocktail",       "category": "drink",     "price": 17.00, "upsell": True},
    {"id": "MI-K04", "name": "Bottle of Wine",       "category": "drink",     "price": 65.00, "upsell": True},
    {"id": "MI-K05", "name": "Coffee / Espresso",    "category": "drink",     "price": 5.00,  "upsell": False},
    # Appetizers
    {"id": "MI-A01", "name": "Soup of the Day",      "category": "appetizer", "price": 9.00,  "upsell": False},
    {"id": "MI-A02", "name": "Caesar Salad",         "category": "appetizer", "price": 12.00, "upsell": False},
    {"id": "MI-A03", "name": "Shrimp Cocktail",      "category": "appetizer", "price": 18.00, "upsell": True},
    {"id": "MI-A04", "name": "Charcuterie Board",    "category": "appetizer", "price": 24.00, "upsell": True},
    # Entrees
    {"id": "MI-E01", "name": "Chicken Marsala",      "category": "entree",    "price": 28.00, "upsell": False},
    {"id": "MI-E02", "name": "Vegetable Risotto",    "category": "entree",    "price": 26.00, "upsell": False},
    {"id": "MI-E03", "name": "Pan-Seared Salmon",    "category": "entree",    "price": 34.00, "upsell": False},
    {"id": "MI-E04", "name": "Lobster Ravioli",      "category": "entree",    "price": 38.00, "upsell": True},
    {"id": "MI-E05", "name": "NY Strip 12oz",        "category": "entree",    "price": 46.00, "upsell": True},
    {"id": "MI-E06", "name": "Filet Mignon 8oz",     "category": "entree",    "price": 58.00, "upsell": True},
    # Desserts
    {"id": "MI-D01", "name": "Seasonal Sorbet",      "category": "dessert",   "price": 9.00,  "upsell": False},
    {"id": "MI-D02", "name": "Crème Brûlée",         "category": "dessert",   "price": 12.00, "upsell": True},
    {"id": "MI-D03", "name": "Chocolate Lava Cake",  "category": "dessert",   "price": 14.00, "upsell": True},
]

_ITEMS_BY_CAT: dict[str, list[dict]] = {}
for _item in MENU_ITEMS:
    _ITEMS_BY_CAT.setdefault(_item["category"], []).append(_item)


def generate_order_items(
    rng: random.Random,
    covers: int,
    opened: datetime,
) -> list[dict]:
    """
    Generate realistic menu item fire times for a single check.
    Items are tagged with sentAt timestamps so callers can filter by sim_time.
      - Drinks:      ordered 2-5 min after seating
      - Appetizers:  40 % of tables, ordered 8-15 min in
      - Entrees:     everyone, ordered 15-25 min in
      - Desserts:    35 % of tables, ordered 50-70 min in
    """
    items = []
    _ts = lambda offset: (opened + offset).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    # Drinks
    drink_off = timedelta(minutes=rng.randint(2, 5))
    for _ in range(covers):
        d = rng.choice(_ITEMS_BY_CAT["drink"])
        items.append({
            "menuItemId": d["id"], "name": d["name"], "category": "drink",
            "quantity": 1, "unitPrice": d["price"],
            "sentAt": _ts(drink_off), "isUpsell": d["upsell"],
        })

    # Appetizers (shared)
    if rng.random() < 0.40:
        app_off = timedelta(minutes=rng.randint(8, 15))
        for _ in range(rng.randint(1, max(1, covers // 2))):
            a = rng.choice(_ITEMS_BY_CAT["appetizer"])
            items.append({
                "menuItemId": a["id"], "name": a["name"], "category": "appetizer",
                "quantity": 1, "unitPrice": a["price"],
                "sentAt": _ts(app_off), "isUpsell": a["upsell"],
            })

    # Entrees
    entree_off = timedelta(minutes=rng.randint(15, 25))
    for _ in range(covers):
        e = rng.choice(_ITEMS_BY_CAT["entree"])
        items.append({
            "menuItemId": e["id"], "name": e["name"], "category": "entree",
            "quantity": 1, "unitPrice": e["price"],
            "sentAt": _ts(entree_off), "isUpsell": e["upsell"],
        })

    # Desserts (shared)
    if rng.random() < 0.35:
        dessert_off = timedelta(minutes=rng.randint(50, 70))
        for _ in range(rng.randint(1, max(1, covers // 2))):
            ds = rng.choice(_ITEMS_BY_CAT["dessert"])
            items.append({
                "menuItemId": ds["id"], "name": ds["name"], "category": "dessert",
                "quantity": 1, "unitPrice": ds["price"],
                "sentAt": _ts(dessert_off), "isUpsell": ds["upsell"],
            })

    return items

EMPLOYEES = [
    {"guid": "emp-0001", "firstName": "Jordan",  "lastName": "Hayes"},
    {"guid": "emp-0002", "firstName": "Maria",   "lastName": "Santos"},
    {"guid": "emp-0003", "firstName": "Devon",   "lastName": "Clarke"},
    {"guid": "emp-0004", "firstName": "Priya",   "lastName": "Nair"},
    {"guid": "emp-0005", "firstName": "Marcus",  "lastName": "Webb"},
    {"guid": "emp-0006", "firstName": "Elena",   "lastName": "Kowalski"},
    {"guid": "emp-0007", "firstName": "James",   "lastName": "Okafor"},
    {"guid": "emp-0008", "firstName": "Sophia",  "lastName": "Chen"},
]

TABLES = [
    {"guid": f"tbl-{i:04d}", "number": str(i), "capacity": cap}
    for i, cap in enumerate([
        2, 2, 4, 4, 4, 4, 6, 6, 2, 2,
        4, 4, 8, 2, 4, 4, 6, 2, 4, 4,
    ], start=1)
]

TABLE_BY_GUID = {t["guid"]: t for t in TABLES}
EMPLOYEE_BY_GUID = {e["guid"]: e for e in EMPLOYEES}


# ---------------------------------------------------------------------------
# Response shape helpers — match exact Toast API schema
# ---------------------------------------------------------------------------

def ext_ref(guid: str, entity_type: str) -> dict:
    return {"guid": guid, "entityType": entity_type, "externalId": guid}


def employee_object(emp: dict) -> dict:
    return {
        "guid":          emp["guid"],
        "entityType":    "Employee",
        "externalId":    emp["guid"],
        "firstName":     emp["firstName"],
        "chosenName":    None,
        "lastName":      emp["lastName"],
        "email":         f"{emp['firstName'].lower()}.{emp['lastName'].lower()}@restaurant.mock",
        "phoneNumber":   None,
        "jobReferences": [ext_ref(JOB_GUID, "Job")],
        "wageOverrides": [],
        "deleted":       False,
        "createdDate":   "2024-01-01T00:00:00.000Z",
        "modifiedDate":  "2024-01-01T00:00:00.000Z",
    }


def payment_object(rng: random.Random, subtotal: float) -> dict:
    tip_pct = rng.uniform(0.16, 0.26)
    tip = round(subtotal * tip_pct, 2)
    p_type = rng.choices(
        ["CREDIT", "CASH", "GIFTCARD"],
        weights=[80, 15, 5],
    )[0]
    return {
        "guid":          f"pay-{rng.randint(100000, 999999)}",
        "entityType":    "Payment",
        "type":          p_type,
        "amount":        subtotal,
        "tipAmount":     tip,
        "amountTendered": round(subtotal + tip, 2),
        "cardType":      "VISA" if p_type == "CREDIT" else None,
        "paymentStatus": "CAPTURED" if p_type == "CREDIT" else "CLOSED",
        "paidDate":      None,   # filled by caller
    }


def check_object(
    rng: random.Random,
    check_guid: str,
    opened: datetime,
    closed: datetime | None,
) -> dict:
    covers = rng.choices([1, 2, 3, 4, 5, 6], weights=[5, 35, 15, 25, 12, 8])[0]
    per_cover = rng.uniform(28, 72)
    subtotal = round(covers * per_cover, 2)
    tax = round(subtotal * 0.085, 2)
    payments = []
    if closed:
        pmt = payment_object(rng, subtotal)
        pmt["paidDate"] = closed.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        payments = [pmt]
    items = generate_order_items(rng, covers, opened)
    return {
        "guid":          check_guid,
        "entityType":    "Check",
        "externalId":    check_guid,
        "openedDate":    opened.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "closedDate":    closed.strftime("%Y-%m-%dT%H:%M:%S.000Z") if closed else None,
        "amount":        subtotal,
        "taxAmount":     tax,
        "totalAmount":   round(subtotal + tax, 2),
        "paymentStatus": "CLOSED" if closed else "OPEN",
        "duration":      int((closed - opened).total_seconds()) if closed else None,
        "payments":      payments,
        "items":         items,
        "deleted":       False,
    }, covers


def order_object(
    rng: random.Random,
    order_guid: str,
    server_guid: str,
    table_guid: str,
    opened: datetime,
    closed: datetime | None,
) -> dict:
    check_guid = f"chk-{order_guid[4:]}"
    check, covers = check_object(rng, check_guid, opened, closed)
    return {
        "guid":           order_guid,
        "entityType":     "Order",
        "externalId":     order_guid,
        "openedDate":     opened.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "closedDate":     closed.strftime("%Y-%m-%dT%H:%M:%S.000Z") if closed else None,
        "displayState":   "CLOSED" if closed else "OPEN",
        "displayNumber":  str(rng.randint(100, 999)),
        "numberOfGuests": covers,
        "voided":         False,
        "deleted":        False,
        "server":         ext_ref(server_guid, "Employee"),
        "table":          ext_ref(table_guid, "Table"),
        "checks":         [check],
        "createdDate":    opened.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "modifiedDate":   (closed or opened).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
    }


def shift_object(
    emp_guid: str,
    clock_in: datetime,
    clock_out: datetime | None,
) -> dict:
    return {
        "guid":              f"shf-{emp_guid}",
        "entityType":        "Shift",
        "externalId":        f"shf-{emp_guid}",
        "employeeReference": ext_ref(emp_guid, "Employee"),
        "jobReference":      ext_ref(JOB_GUID, "Job"),
        "inDate":            clock_in.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "outDate":           clock_out.strftime("%Y-%m-%dT%H:%M:%S.000Z") if clock_out else None,
        "deleted":           False,
        "createdDate":       clock_in.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "modifiedDate":      (clock_out or clock_in).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
    }


# ---------------------------------------------------------------------------
# Service generators
# ---------------------------------------------------------------------------

def _service_anchor(date: datetime) -> datetime:
    """Service start — 5:00 PM on the given date (UTC)."""
    return date.replace(hour=17, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)


def generate_employees() -> list[dict]:
    return [employee_object(e) for e in EMPLOYEES]


def generate_shifts(
    date: datetime,
    mode: str,
    sim_time: datetime | None = None,
) -> list[dict]:
    rng = random.Random(date.toordinal())
    service_start = _service_anchor(date)
    now = sim_time or datetime.now(timezone.utc)
    shifts = []

    for emp in EMPLOYEES:
        clock_in = service_start + timedelta(minutes=rng.randint(-20, 10))
        clock_out_candidate = service_start + timedelta(hours=rng.uniform(5.5, 7.5))
        if mode == "live":
            # Still on shift if sim/real time hasn't passed their clock-out
            clock_out = None if now < clock_out_candidate else clock_out_candidate
        else:
            clock_out = clock_out_candidate
        shifts.append(shift_object(emp["guid"], clock_in, clock_out))

    return shifts


def generate_orders(
    start: datetime,
    end: datetime,
    mode: str,
    sim_time: datetime | None = None,
) -> list[dict]:
    date = start.date()
    rng = random.Random(date.toordinal() + 1)
    service_start = _service_anchor(
        datetime(date.year, date.month, date.day)
    )
    now = sim_time or datetime.now(timezone.utc)

    emp_guids = [e["guid"] for e in EMPLOYEES]
    tbl_guids = [t["guid"] for t in TABLES]

    # Assign sections — each server covers 2-3 tables
    server_tables: dict[str, list[str]] = {g: [] for g in emp_guids}
    for i, tbl in enumerate(tbl_guids):
        server_tables[emp_guids[i % len(emp_guids)]].append(tbl)

    num_orders = rng.randint(28, 42)
    orders = []

    for i in range(num_orders):
        order_guid = f"ord-{date.strftime('%Y%m%d')}-{i:03d}"
        server_guid = rng.choice(emp_guids)
        table_guid = rng.choice(server_tables[server_guid])

        offset = timedelta(minutes=rng.randint(0, 270))
        opened = service_start + offset
        turn_time = timedelta(minutes=rng.randint(38, 95))
        closed_candidate = opened + turn_time

        if mode == "live":
            if closed_candidate <= now - timedelta(minutes=10):
                closed = closed_candidate
            elif opened > now:
                continue   # not seated yet at sim_time
            else:
                closed = None
        else:
            closed = closed_candidate

        if opened < start or opened >= end:
            continue

        orders.append(
            order_object(rng, order_guid, server_guid, table_guid, opened, closed)
        )

    return orders
