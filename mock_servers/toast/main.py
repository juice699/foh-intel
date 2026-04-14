"""
Toast API mock server.
Run: uvicorn mock_servers.toast.main:app --port 8001 --reload
"""
import uvicorn
from fastapi import FastAPI
from mock_servers.toast.routes import auth, employees, orders, shifts

app = FastAPI(
    title="Toast API — Mock",
    description="1-for-1 mock of the Toast REST API for local development.",
    version="1.0.0",
)

app.include_router(auth.router,      prefix="/authentication/v1")
app.include_router(employees.router, prefix="/employees/v1")
app.include_router(orders.router,    prefix="/orders/v2")
app.include_router(shifts.router,    prefix="/labor/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "server": "toast-mock"}


if __name__ == "__main__":
    import os
    port = int(os.getenv("TOAST_MOCK_PORT", 8001))
    uvicorn.run("mock_servers.toast.main:app", host="0.0.0.0", port=port, reload=True)
