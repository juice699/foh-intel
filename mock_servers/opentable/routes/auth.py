from fastapi import APIRouter, Form, HTTPException

router = APIRouter(tags=["auth"])

MOCK_TOKEN = "mock-opentable-bearer-token"


@router.post("/oauth/token")
async def token(
    grant_type:    str = Form(...),
    client_id:     str = Form(...),
    client_secret: str = Form(...),
):
    if grant_type != "client_credentials":
        raise HTTPException(status_code=400, detail="grant_type must be client_credentials")
    return {
        "access_token": MOCK_TOKEN,
        "token_type":   "Bearer",
        "expires_in":   3600,
    }
