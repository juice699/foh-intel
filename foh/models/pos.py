from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class OrderStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    VOIDED = "voided"


class PaymentMethod(str, Enum):
    CREDIT = "credit"
    CASH = "cash"
    GIFT_CARD = "gift_card"
    OTHER = "other"


class OrderItem(BaseModel):
    """A single fired menu item on a check."""
    name:     str
    category: str          # "drink" | "appetizer" | "entree" | "dessert"
    quantity: int  = 1
    price:    Decimal
    sent_at:  datetime     # When sent to kitchen / recorded in POS
    is_upsell: bool = False


class Server(BaseModel):
    """Normalized server/employee record from POS."""
    provider_id: str                        # Raw ID from source system
    name: str
    email: Optional[str] = None
    role: Optional[str] = None             # e.g. "Server", "Bartender", "Support"
    active: bool = True


class Check(BaseModel):
    """A single guest check — the atomic unit of server performance."""
    provider_id: str
    server_id: str                          # References Server.provider_id
    table_id: str
    opened_at: datetime
    closed_at: Optional[datetime] = None
    covers: int = Field(ge=0)              # Number of guests
    subtotal: Decimal = Field(ge=0)
    tax: Decimal = Field(ge=0)
    tip: Optional[Decimal] = None
    payment_method: Optional[PaymentMethod] = None
    status: OrderStatus = OrderStatus.OPEN
    items: list[OrderItem] = []

    @property
    def turn_time_minutes(self) -> Optional[float]:
        if self.closed_at and self.opened_at:
            return (self.closed_at - self.opened_at).total_seconds() / 60
        return None

    @property
    def tip_percentage(self) -> Optional[float]:
        if self.tip is not None and self.subtotal > 0:
            return float(self.tip / self.subtotal * 100)
        return None

    @property
    def revenue_per_cover(self) -> Optional[float]:
        if self.covers > 0:
            return float(self.subtotal / self.covers)
        return None


class Shift(BaseModel):
    """A server's work shift — aggregation context for Check data."""
    provider_id: str
    server_id: str
    date: datetime
    clock_in: datetime
    clock_out: Optional[datetime] = None
    section: Optional[str] = None          # Floor section assigned
