from fastapi import APIRouter, Header, Query, HTTPException, Path
from datetime import datetime, timezone
from mock_servers.opentable.data import generate_reservations
import os

router = APIRouter(tags=["reservations"])


def _require_auth(authorization: str | None) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")


@router.get("/restaurants/{restaurant_id}/reservations")
async def get_reservations(
    restaurant_id: str = Path(...),
    date:          str = Query(...),
    status:        str = Query(default="booked,seated,completed,no_show"),
    authorization: str | None = Header(default=None),
    _mode: str | None = Query(default=None, include_in_schema=False),
):
    _require_auth(authorization)
    try:
        dt = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {date} — expected YYYY-MM-DD")

    mode         = _mode or os.getenv("DATA_MODE", "live")
    requested    = set(status.split(","))
    reservations = generate_reservations(dt, mode)
    filtered     = [r for r in reservations if r["status"] in requested]
    return {"reservations": filtered}


@router.patch("/restaurants/{restaurant_id}/reservations/{reservation_id}")
async def update_reservation(
    restaurant_id:  str = Path(...),
    reservation_id: str = Path(...),
    body:           dict = None,
    authorization:  str | None = Header(default=None),
):
    _require_auth(authorization)
    # Mock write-back — return the posted fields merged into a stub reservation
    return {
        "id":              reservation_id,
        "guestName":       "Mock Guest",
        "partySize":       2,
        "dateTime":        datetime.now(timezone.utc).isoformat(),
        "status":          "seated",
        "isVip":           False,
        "specialRequests": [],
        **(body or {}),
    }
