from abc import ABC, abstractmethod
from datetime import datetime
from foh.models.pos import Server, Check, Shift
from foh.models.reservations import Guest, Reservation


class POSProvider(ABC):
    """
    Abstract interface for POS integrations.
    Implement this to add Toast, Square, or any other POS system.
    All methods return normalized internal models — no raw API types leak out.
    """

    @abstractmethod
    async def authenticate(self) -> None:
        """Perform auth handshake and store credentials internally."""
        ...

    @abstractmethod
    async def get_servers(self) -> list[Server]:
        """Return all active FOH staff."""
        ...

    @abstractmethod
    async def get_checks(self, date: datetime) -> list[Check]:
        """Return all checks for a given service date."""
        ...

    @abstractmethod
    async def get_shifts(self, date: datetime) -> list[Shift]:
        """Return all server shifts for a given service date."""
        ...


class ReservationProvider(ABC):
    """
    Abstract interface for reservation/booking integrations.
    Implement this to add OpenTable, Resy, SevenRooms, or any other system.
    """

    @abstractmethod
    async def authenticate(self) -> None:
        """Perform auth handshake and store credentials internally."""
        ...

    @abstractmethod
    async def get_reservations(self, date: datetime) -> list[Reservation]:
        """Return all reservations for a given service date."""
        ...

    @abstractmethod
    async def get_guests(self, guest_ids: list[str]) -> list[Guest]:
        """Return guest profiles for a list of provider-specific guest IDs."""
        ...

    @abstractmethod
    async def update_reservation(self, reservation_id: str, **kwargs) -> Reservation:
        """Update reservation fields — table assignment, server, status, etc."""
        ...
