from fastapi import APIRouter, Header, HTTPException
from mock_servers.toast.data import generate_employees

router = APIRouter(tags=["employees"])


def _require_auth(authorization: str | None) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")


@router.get("/employees")
async def get_employees(
    authorization: str | None = Header(default=None),
    toast_restaurant_external_id: str | None = Header(default=None, alias="Toast-Restaurant-External-ID"),
):
    _require_auth(authorization)
    return generate_employees()
