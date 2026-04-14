from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(tags=["auth"])

MOCK_TOKEN = "mock-toast-bearer-token"


class AuthRequest(BaseModel):
    clientId: str
    clientSecret: str
    userAccessType: str


@router.post("/authentication/login")
async def login(body: AuthRequest):
    if body.userAccessType != "TOAST_MACHINE_CLIENT":
        raise HTTPException(status_code=400, detail="userAccessType must be TOAST_MACHINE_CLIENT")
    return {
        "status": "SUCCESS",
        "token": {
            "accessToken": MOCK_TOKEN,
            "tokenType":   "Bearer",
            "expiresIn":   3600,
            "scope":       None,
        },
    }
