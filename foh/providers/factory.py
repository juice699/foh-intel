"""
Provider factory — single entry point for the rest of the application.
Swap APP_ENV in .env to move between development, sandbox, and production.
No code changes required anywhere else.
"""
from foh.providers.base import POSProvider, ReservationProvider
from foh.providers.pos.toast import ToastPOSProvider
from foh.providers.reservations.opentable import OpenTableReservationProvider
from foh.config import settings


def get_pos_provider() -> POSProvider:
    """
    Returns the active POS provider for the current APP_ENV.
    Currently only Toast is implemented. Add Square, Lightspeed, etc. here.
    """
    return ToastPOSProvider()


def get_reservation_provider() -> ReservationProvider:
    """
    Returns the active reservation provider for the current APP_ENV.
    Currently only OpenTable is implemented. Add Resy, SevenRooms, etc. here.
    """
    return OpenTableReservationProvider()


def env_label() -> str:
    return settings.app_env.upper()
