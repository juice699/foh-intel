from fastapi import APIRouter, Header, HTTPException, Path
from mock_servers.opentable.data import generate_guest

router = APIRouter(tags=["guests"])


def _require_auth(authorization: str | None) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")


@router.get("/restaurants/{restaurant_id}/guests/{guest_id}")
async def get_guest(
    restaurant_id: str = Path(...),
    guest_id:      str = Path(...),
    authorization: str | None = Header(default=None),
):
    _require_auth(authorization)
    return generate_guest(guest_id)
