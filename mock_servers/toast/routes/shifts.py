from fastapi import APIRouter, Header, Query, HTTPException
from datetime import datetime, timezone
from mock_servers.toast.data import generate_shifts
import os

router = APIRouter(tags=["shifts"])


def _require_auth(authorization: str | None) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")


def _parse_dt(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {value}")


@router.get("/shifts")
async def get_shifts(
    startDate: str = Query(...),
    endDate:   str = Query(...),
    authorization: str | None = Header(default=None),
    toast_restaurant_external_id: str | None = Header(default=None, alias="Toast-Restaurant-External-ID"),
    _mode: str | None = Query(default=None, include_in_schema=False),
):
    _require_auth(authorization)
    date = _parse_dt(startDate)
    mode = _mode or os.getenv("DATA_MODE", "live")
    return generate_shifts(date, mode)
