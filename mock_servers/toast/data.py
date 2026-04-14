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


def generate_shifts(date: datetime, mode: str) -> list[dict]:
    rng = random.Random(date.toordinal())
    service_start = _service_anchor(date)
    now = datetime.now(timezone.utc)
    shifts = []

    for emp in EMPLOYEES:
        clock_in = service_start + timedelta(minutes=rng.randint(-20, 10))
        if mode == "live" and date.date() == now.date():
            clock_out = None   # still on shift
        else:
            clock_out = service_start + timedelta(hours=rng.uniform(5.5, 7.5))
        shifts.append(shift_object(emp["guid"], clock_in, clock_out))

    return shifts


def generate_orders(start: datetime, end: datetime, mode: str) -> list[dict]:
    date = start.date()
    rng = random.Random(date.toordinal() + 1)
    service_start = _service_anchor(
        datetime(date.year, date.month, date.day)
    )
    now = datetime.now(timezone.utc)

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

        # Stagger seatings across the service window (5pm – 9:30pm)
        offset = timedelta(minutes=rng.randint(0, 270))
        opened = service_start + offset
        turn_time = timedelta(minutes=rng.randint(38, 95))
        closed_candidate = opened + turn_time

        if mode == "live" and date == now.date():
            # Orders closed more than 10 min ago are settled
            # Orders still within their turn time stay open
            if closed_candidate <= now - timedelta(minutes=10):
                closed = closed_candidate
            elif opened > now:
                continue   # hasn't been seated yet — don't include
            else:
                closed = None
        else:
            closed = closed_candidate

        # Only include if it falls within the requested window
        if opened < start or opened >= end:
            continue

        orders.append(
            order_object(rng, order_guid, server_guid, table_guid, opened, closed)
        )

    return orders
