import httpx
from datetime import datetime, timezone, timedelta
from foh.providers.base import ReservationProvider
from foh.models.reservations import Guest, Reservation, ReservationStatus, DiningPreference
from foh.config import settings


STATUS_MAP = {
    "booked":    ReservationStatus.BOOKED,
    "seated":    ReservationStatus.SEATED,
    "completed": ReservationStatus.COMPLETED,
    "no_show":   ReservationStatus.NO_SHOW,
    "cancelled": ReservationStatus.CANCELLED,
}

PREFERENCE_MAP = {
    "window":              DiningPreference.WINDOW,
    "booth":               DiningPreference.BOOTH,
    "bar":                 DiningPreference.BAR,
    "patio":               DiningPreference.PATIO,
    "quiet section":       DiningPreference.QUIET,
    "high chair":          DiningPreference.HIGH_CHAIR,
    "wheelchair accessible": DiningPreference.ACCESSIBLE,
}


class OpenTableReservationProvider(ReservationProvider):

    def __init__(self):
        self._token: str | None = None
        self._token_expires_at: datetime | None = None
        self._client = httpx.AsyncClient(timeout=30.0)

    @property
    def _base_url(self) -> str:
        return settings.opentable_base_url

    @property
    def _restaurant_id(self) -> str:
        return settings.opentable_restaurant_id

    async def authenticate(self) -> None:
        resp = await self._client.post(
            f"{self._base_url}/oauth/token",
            data={
                "grant_type":    "client_credentials",
                "client_id":     settings.opentable_client_id,
                "client_secret": settings.opentable_client_secret,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        self._token_expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=expires_in - 60)
        )
        self._client.headers.update({"Authorization": f"Bearer {self._token}"})

    async def _ensure_authenticated(self) -> None:
        if self._token is None or datetime.now(timezone.utc) >= self._token_expires_at:
            await self.authenticate()

    async def get_reservations(self, date: datetime) -> list[Reservation]:
        await self._ensure_authenticated()
        params: dict = {
            "date":   date.strftime("%Y-%m-%d"),
            "status": "booked,seated,completed,no_show",
        }
        if settings.app_env == "development":
            params["_mode"] = settings.data_mode
        resp = await self._client.get(
            f"{self._base_url}/restaurants/{self._restaurant_id}/reservations",
            params=params,
        )
        resp.raise_for_status()
        return [
            self._normalize_reservation(r)
            for r in resp.json().get("reservations", [])
        ]

    async def get_guests(self, guest_ids: list[str]) -> list[Guest]:
        await self._ensure_authenticated()
        guests = []
        for guest_id in guest_ids:
            resp = await self._client.get(
                f"{self._base_url}/restaurants/{self._restaurant_id}/guests/{guest_id}"
            )
            if resp.status_code == 200:
                guests.append(self._normalize_guest(resp.json()))
        return guests

    async def update_reservation(self, reservation_id: str, **kwargs) -> Reservation:
        await self._ensure_authenticated()
        resp = await self._client.patch(
            f"{self._base_url}/restaurants/{self._restaurant_id}/reservations/{reservation_id}",
            json=kwargs,
        )
        resp.raise_for_status()
        return self._normalize_reservation(resp.json())

    # --- Normalization helpers ---

    def _normalize_reservation(self, raw: dict) -> Reservation:
        preferences = [
            PREFERENCE_MAP[p.lower()]
            for p in raw.get("specialRequests", [])
            if p.lower() in PREFERENCE_MAP
        ]
        return Reservation(
            provider_id=str(raw["id"]),
            guest_id=str(raw["guestId"]) if raw.get("guestId") else None,
            guest_name=raw.get("guestName", ""),
            party_size=raw["partySize"],
            scheduled_at=datetime.fromisoformat(raw["dateTime"]),
            seated_at=datetime.fromisoformat(raw["seatedAt"])
                if raw.get("seatedAt") else None,
            status=STATUS_MAP.get(raw.get("status", "booked"), ReservationStatus.BOOKED),
            table_id=str(raw["tableId"]) if raw.get("tableId") else None,
            server_id=str(raw["serverId"]) if raw.get("serverId") else None,
            notes=raw.get("notes"),
            preferences=preferences,
            is_vip=raw.get("isVip", False),
        )

    def _normalize_guest(self, raw: dict) -> Guest:
        preferences = [
            PREFERENCE_MAP[p.lower()]
            for p in raw.get("diningPreferences", [])
            if p.lower() in PREFERENCE_MAP
        ]
        return Guest(
            provider_id=str(raw["id"]),
            first_name=raw.get("firstName", ""),
            last_name=raw.get("lastName", ""),
            email=raw.get("email"),
            phone=raw.get("phone"),
            visit_count=raw.get("visitCount", 0),
            notes=raw.get("notes"),
            preferences=preferences,
        )
