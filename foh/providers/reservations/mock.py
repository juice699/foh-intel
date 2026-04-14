"""
Mock reservation provider for local development.
Generates realistic-looking FOH data so the pipeline and scoring engine
can be built and tested without an approved OpenTable partner account.
Replace with OpenTableReservationProvider once credentials are obtained.
"""
import random
from datetime import datetime, timedelta
from foh.providers.base import ReservationProvider
from foh.models.reservations import Guest, Reservation, ReservationStatus, DiningPreference


_FIRST_NAMES = ["James", "Maria", "Chen", "Sophia", "Marcus", "Elena", "David", "Priya"]
_LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Taylor", "Anderson", "Lee", "Patel"]

_NOTES_POOL = [
    "Anniversary dinner",
    "Birthday celebration",
    "Business dinner",
    "Regular guest — prefers back booth",
    "Nut allergy — notify kitchen",
    None, None, None,  # weighted toward no notes
]


class MockReservationProvider(ReservationProvider):
    """
    Generates deterministic-ish reservation and guest data for a service date.
    Seed is based on the date so the same date always returns the same data.
    """

    async def authenticate(self) -> None:
        pass  # No auth needed for mock

    async def get_reservations(self, date: datetime) -> list[Reservation]:
        rng = random.Random(date.toordinal())
        reservations = []
        service_start = date.replace(hour=17, minute=0, second=0)

        for i in range(rng.randint(18, 32)):
            offset_minutes = rng.randint(0, 180)
            scheduled = service_start + timedelta(minutes=offset_minutes)
            party_size = rng.choices([2, 3, 4, 5, 6, 8], weights=[35, 15, 25, 10, 10, 5])[0]
            status = rng.choices(
                [ReservationStatus.COMPLETED, ReservationStatus.NO_SHOW, ReservationStatus.BOOKED],
                weights=[80, 8, 12],
            )[0]
            seated_at = None
            if status == ReservationStatus.COMPLETED:
                wait = rng.randint(-5, 20)  # negative = seated early
                seated_at = scheduled + timedelta(minutes=wait)

            prefs = rng.sample(list(DiningPreference), k=rng.randint(0, 2))

            reservations.append(Reservation(
                provider_id=f"mock-res-{date.strftime('%Y%m%d')}-{i:03d}",
                guest_id=f"mock-guest-{i:04d}",
                guest_name=f"{rng.choice(_FIRST_NAMES)} {rng.choice(_LAST_NAMES)}",
                party_size=party_size,
                scheduled_at=scheduled,
                seated_at=seated_at,
                status=status,
                table_id=f"T{rng.randint(1, 20):02d}",
                notes=rng.choice(_NOTES_POOL),
                preferences=prefs,
                is_vip=rng.random() < 0.08,
            ))

        return sorted(reservations, key=lambda r: r.scheduled_at)

    async def get_guests(self, guest_ids: list[str]) -> list[Guest]:
        guests = []
        for guest_id in guest_ids:
            seed = int(guest_id.split("-")[-1]) if guest_id.split("-")[-1].isdigit() else 0
            rng = random.Random(seed)
            guests.append(Guest(
                provider_id=guest_id,
                first_name=rng.choice(_FIRST_NAMES),
                last_name=rng.choice(_LAST_NAMES),
                email=f"guest{seed}@example.com",
                visit_count=rng.randint(0, 24),
                preferences=rng.sample(list(DiningPreference), k=rng.randint(0, 2)),
            ))
        return guests

    async def update_reservation(self, reservation_id: str, **kwargs) -> Reservation:
        raise NotImplementedError("MockReservationProvider does not support writes.")
