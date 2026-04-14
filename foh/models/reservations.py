from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class ReservationStatus(str, Enum):
    BOOKED = "booked"
    SEATED = "seated"
    COMPLETED = "completed"
    NO_SHOW = "no_show"
    CANCELLED = "cancelled"


class DiningPreference(str, Enum):
    WINDOW = "window"
    BOOTH = "booth"
    BAR = "bar"
    PATIO = "patio"
    QUIET = "quiet"
    HIGH_CHAIR = "high_chair"
    ACCESSIBLE = "accessible"


class Guest(BaseModel):
    """Normalized guest profile."""
    provider_id: str
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    visit_count: int = 0
    notes: Optional[str] = None            # VIP notes, allergies, preferences
    preferences: list[DiningPreference] = Field(default_factory=list)


class Reservation(BaseModel):
    """A single reservation record."""
    provider_id: str
    guest_id: Optional[str] = None         # References Guest.provider_id if known
    guest_name: str                         # Display name fallback
    party_size: int = Field(ge=1)
    scheduled_at: datetime
    seated_at: Optional[datetime] = None
    status: ReservationStatus = ReservationStatus.BOOKED
    table_id: Optional[str] = None
    server_id: Optional[str] = None        # Assigned after seating
    notes: Optional[str] = None
    preferences: list[DiningPreference] = Field(default_factory=list)
    is_vip: bool = False

    @property
    def wait_minutes(self) -> Optional[float]:
        """Time between reservation and actual seating."""
        if self.seated_at and self.scheduled_at:
            delta = (self.seated_at - self.scheduled_at).total_seconds() / 60
            return max(delta, 0.0)
        return None
