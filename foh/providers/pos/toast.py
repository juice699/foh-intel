import httpx
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from foh.providers.base import POSProvider
from foh.models.pos import Server, Check, Shift, OrderStatus, PaymentMethod
from foh.config import settings


# Payment type enum — must match Toast API exactly (GIFTCARD, not GIFT_CARD)
PAYMENT_METHOD_MAP = {
    "CASH":          PaymentMethod.CASH,
    "CREDIT":        PaymentMethod.CREDIT,
    "GIFTCARD":      PaymentMethod.GIFT_CARD,
    "HOUSE_ACCOUNT": PaymentMethod.OTHER,
    "REWARDCARD":    PaymentMethod.OTHER,
    "OTHER":         PaymentMethod.OTHER,
}

ORDER_STATUS_MAP = {
    "OPEN":   OrderStatus.OPEN,
    "CLOSED": OrderStatus.CLOSED,
    "VOIDED": OrderStatus.VOIDED,
}


class ToastPOSProvider(POSProvider):

    def __init__(self):
        self._token: str | None = None
        self._token_expires_at: datetime | None = None
        self._client = httpx.AsyncClient(timeout=30.0)

    @property
    def _base_url(self) -> str:
        # Resolved at call time so APP_ENV changes are respected
        return settings.toast_base_url

    async def authenticate(self) -> None:
        resp = await self._client.post(
            f"{self._base_url}/authentication/v1/authentication/login",
            json={
                "clientId":      settings.toast_client_id,
                "clientSecret":  settings.toast_client_secret,
                "userAccessType": "TOAST_MACHINE_CLIENT",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["token"]["accessToken"]
        expires_in = data["token"].get("expiresIn", 3600)
        self._token_expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=expires_in - 60)
        )
        self._client.headers.update({
            "Authorization":               f"Bearer {self._token}",
            "Toast-Restaurant-External-ID": settings.toast_restaurant_guid,
        })

    async def _ensure_authenticated(self) -> None:
        if self._token is None or datetime.now(timezone.utc) >= self._token_expires_at:
            await self.authenticate()

    async def get_servers(self) -> list[Server]:
        await self._ensure_authenticated()
        resp = await self._client.get(f"{self._base_url}/employees/v1/employees")
        resp.raise_for_status()
        return [self._normalize_employee(e) for e in resp.json()]

    async def get_checks(self, date: datetime) -> list[Check]:
        await self._ensure_authenticated()
        start = date.replace(hour=0,  minute=0,  second=0,  microsecond=0).isoformat() + "Z"
        end   = date.replace(hour=23, minute=59, second=59, microsecond=0).isoformat() + "Z"
        params: dict = {"startDate": start, "endDate": end}
        if settings.app_env == "development":
            params["_mode"] = settings.data_mode
        resp = await self._client.get(
            f"{self._base_url}/orders/v2/ordersBulk",
            params=params,
        )
        resp.raise_for_status()
        checks = []
        for order in resp.json():
            for check in order.get("checks", []):
                checks.append(self._normalize_check(check, order))
        return checks

    async def get_shifts(self, date: datetime) -> list[Shift]:
        await self._ensure_authenticated()
        start = date.replace(hour=0,  minute=0,  second=0,  microsecond=0).isoformat() + "Z"
        end   = date.replace(hour=23, minute=59, second=59, microsecond=0).isoformat() + "Z"
        params: dict = {"startDate": start, "endDate": end}
        if settings.app_env == "development":
            params["_mode"] = settings.data_mode
        resp = await self._client.get(
            f"{self._base_url}/labor/v1/shifts",
            params=params,
        )
        resp.raise_for_status()
        return [self._normalize_shift(s) for s in resp.json()]

    # --- Normalization helpers ---

    def _normalize_employee(self, raw: dict) -> Server:
        # jobReferences is an array of ExternalReference objects
        job_refs = raw.get("jobReferences", [])
        role = job_refs[0].get("entityType") if job_refs else None
        # Use chosenName if present, fall back to firstName
        first = raw.get("chosenName") or raw.get("firstName", "")
        return Server(
            provider_id=raw["guid"],
            name=f"{first} {raw.get('lastName', '')}".strip(),
            email=raw.get("email"),
            role=role,
            active=not raw.get("deleted", False),
        )

    def _normalize_check(self, check: dict, order: dict) -> Check:
        payments = check.get("payments", [])
        tip = sum(Decimal(str(p.get("tipAmount", 0))) for p in payments)
        payment_type = None
        if payments:
            raw_type = payments[0].get("type", "").upper()
            payment_type = PAYMENT_METHOD_MAP.get(raw_type, PaymentMethod.OTHER)

        # numberOfGuests lives on the Order object per the official schema
        covers = order.get("numberOfGuests", 0)

        return Check(
            provider_id=check["guid"],
            server_id=order.get("server", {}).get("guid", ""),
            table_id=order.get("table", {}).get("guid", ""),
            opened_at=datetime.fromisoformat(
                order["openedDate"].replace("Z", "+00:00")
            ),
            closed_at=datetime.fromisoformat(
                order["closedDate"].replace("Z", "+00:00")
            ) if order.get("closedDate") else None,
            covers=covers,
            subtotal=Decimal(str(check.get("amount", 0))),
            tax=Decimal(str(check.get("taxAmount", 0))),
            tip=tip if tip > 0 else None,
            payment_method=payment_type,
            status=ORDER_STATUS_MAP.get(
                order.get("displayState", "").upper(), OrderStatus.OPEN
            ),
        )

    def _normalize_shift(self, raw: dict) -> Shift:
        # employeeReference is an ExternalReference object
        employee_ref = raw.get("employeeReference", {})
        return Shift(
            provider_id=raw["guid"],
            server_id=employee_ref.get("guid", ""),
            date=datetime.fromisoformat(raw["inDate"].replace("Z", "+00:00")),
            clock_in=datetime.fromisoformat(raw["inDate"].replace("Z", "+00:00")),
            clock_out=datetime.fromisoformat(
                raw["outDate"].replace("Z", "+00:00")
            ) if raw.get("outDate") else None,
        )
