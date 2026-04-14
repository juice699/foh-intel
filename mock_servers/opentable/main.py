"""
OpenTable API mock server.
Run: uvicorn mock_servers.opentable.main:app --port 8002 --reload

All routes are prefixed /v2 to match the real OpenTable API base URL pattern
(providers set base_url to http://localhost:8002/v2 and append routes directly).
"""
import uvicorn
from fastapi import FastAPI
from mock_servers.opentable.routes import auth, reservations, guests

app = FastAPI(
    title="OpenTable API — Mock",
    description="1-for-1 mock of the OpenTable REST API for local development.",
    version="1.0.0",
)

app.include_router(auth.router,         prefix="/v2")
app.include_router(reservations.router, prefix="/v2")
app.include_router(guests.router,       prefix="/v2")


@app.get("/health")
async def health():
    return {"status": "ok", "server": "opentable-mock"}


if __name__ == "__main__":
    import os
    port = int(os.getenv("OPENTABLE_MOCK_PORT", 8002))
    uvicorn.run("mock_servers.opentable.main:app", host="0.0.0.0", port=port, reload=True)
