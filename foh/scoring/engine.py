"""
FOH Intel — Scoring Engine

Two-stage scoring:

  Stage 1 — ServerProfile
    Aggregates a server's historical checks into a performance profile.
    Produces a normalized ServerScore (0.0–1.0) from weighted metrics.

  Stage 2 — SeatingSuggestion
    For each pending reservation, scores every available server against
    the party's needs and current floor state, then returns a ranked
    list of recommendations with plain-English reasoning.

Weights are defined in ScoringWeights and are tunable without touching
any other code. All normalization is relative to the server pool on the
current shift — scores are only meaningful compared to each other, not
in absolute terms.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Optional

from foh.models.pos import Check, Server, Shift
from foh.models.reservations import DiningPreference, Reservation


# ---------------------------------------------------------------------------
# Tunable weights
# ---------------------------------------------------------------------------

@dataclass
class ScoringWeights:
    """
    All weights must sum to 1.0 within each group.
    Adjust these to reflect what matters most in a specific restaurant.
    """

    # --- Server performance weights (Stage 1) ---
    # How much each metric contributes to the overall ServerScore
    tip_rate:         float = 0.30   # Guest satisfaction proxy
    turn_consistency: float = 0.25   # Predictable pacing = better floor management
    covers_capacity:  float = 0.20   # Ability to handle volume
    revenue_per_cover: float = 0.15  # Upsell effectiveness
    turn_speed:       float = 0.10   # Raw throughput

    # --- Match score weights (Stage 2) ---
    # How much each factor shifts a server's suitability for a specific party
    server_performance: float = 0.40  # Base server quality
    floor_balance:      float = 0.30  # Distributing load evenly across servers
    party_fit:          float = 0.20  # Party size vs. server's historical sweet spot
    vip_readiness:      float = 0.10  # VIP/high-value guest handling

    def validate(self) -> None:
        perf = self.tip_rate + self.turn_consistency + self.covers_capacity
        perf += self.revenue_per_cover + self.turn_speed
        match = self.server_performance + self.floor_balance + self.party_fit
        match += self.vip_readiness
        assert abs(perf - 1.0) < 1e-6,  f"Performance weights sum to {perf}, must be 1.0"
        assert abs(match - 1.0) < 1e-6, f"Match weights sum to {match}, must be 1.0"


DEFAULT_WEIGHTS = ScoringWeights()


# ---------------------------------------------------------------------------
# Stage 1 — Server performance profile
# ---------------------------------------------------------------------------

@dataclass
class ServerProfile:
    """
    Computed from a server's closed checks over a shift or date range.
    All raw metrics are stored so the dashboard can surface them directly.
    """
    server: Server

    # Raw aggregates
    check_count:       int   = 0
    total_covers:      int   = 0
    avg_tip_pct:       float = 0.0
    avg_turn_minutes:  float = 0.0
    turn_stdev:        float = 0.0   # Lower = more consistent pacing
    avg_revenue_cover: float = 0.0

    # Current floor state (populated separately for live mode)
    open_tables:       int   = 0     # Tables currently open/active
    open_covers:       int   = 0     # Covers currently on the floor

    # Normalized score 0.0–1.0 (set after pool normalization)
    performance_score: float = 0.0

    @classmethod
    def from_checks(cls, server: Server, checks: list[Check]) -> ServerProfile:
        closed = [c for c in checks if c.closed_at and c.server_id == server.provider_id]
        open_  = [c for c in checks if not c.closed_at and c.server_id == server.provider_id]

        if not closed:
            return cls(
                server=server,
                open_tables=len(open_),
                open_covers=sum(c.covers for c in open_),
            )

        turns    = [c.turn_time_minutes for c in closed if c.turn_time_minutes is not None]
        tips     = [c.tip_percentage    for c in closed if c.tip_percentage    is not None]
        rev_cov  = [c.revenue_per_cover for c in closed if c.revenue_per_cover is not None]

        return cls(
            server=server,
            check_count=len(closed),
            total_covers=sum(c.covers for c in closed),
            avg_tip_pct=statistics.mean(tips)     if tips    else 0.0,
            avg_turn_minutes=statistics.mean(turns) if turns else 0.0,
            turn_stdev=statistics.stdev(turns)    if len(turns) > 1 else 0.0,
            avg_revenue_cover=statistics.mean(rev_cov) if rev_cov else 0.0,
            open_tables=len(open_),
            open_covers=sum(c.covers for c in open_),
        )

    @property
    def is_active(self) -> bool:
        """Has handled at least one table or is currently active."""
        return self.check_count > 0 or self.open_tables > 0


# ---------------------------------------------------------------------------
# Stage 1 — Pool normalization
# ---------------------------------------------------------------------------

def _normalize(value: float, values: list[float], invert: bool = False) -> float:
    """Min-max normalize value within a pool. Invert for metrics where lower = better."""
    if not values or max(values) == min(values):
        return 0.5
    lo, hi = min(values), max(values)
    normalized = (value - lo) / (hi - lo)
    return 1.0 - normalized if invert else normalized


def build_profiles(
    servers:  list[Server],
    checks:   list[Check],
    shifts:   list[Shift],
    weights:  ScoringWeights = DEFAULT_WEIGHTS,
) -> list[ServerProfile]:
    """
    Build and score ServerProfiles for all servers on shift for this service period.
    In live mode: only servers still clocked in (clock_out is None).
    In batch/historical mode: all servers who worked any shift — clock_out may be set.
    """
    weights.validate()
    live_ids  = {s.server_id for s in shifts if s.clock_out is None}
    all_shift_ids = {s.server_id for s in shifts}
    # Use active (clocked-in) servers if any exist; fall back to all shift servers
    active_ids = live_ids if live_ids else all_shift_ids

    profiles = [
        ServerProfile.from_checks(srv, checks)
        for srv in servers
        if srv.provider_id in active_ids
    ]

    if not profiles:
        return []

    # Extract metric pools for normalization
    tips    = [p.avg_tip_pct        for p in profiles]
    turns   = [p.avg_turn_minutes   for p in profiles]
    stdevs  = [p.turn_stdev         for p in profiles]
    covers  = [p.total_covers       for p in profiles]
    rev_cov = [p.avg_revenue_cover  for p in profiles]

    for p in profiles:
        if p.check_count == 0:
            p.performance_score = 0.5   # No data — neutral, not penalized
            continue

        score = (
            weights.tip_rate         * _normalize(p.avg_tip_pct,       tips)           +
            weights.turn_consistency * _normalize(p.turn_stdev,        stdevs, invert=True) +
            weights.covers_capacity  * _normalize(p.total_covers,      covers)         +
            weights.revenue_per_cover * _normalize(p.avg_revenue_cover, rev_cov)       +
            weights.turn_speed       * _normalize(p.avg_turn_minutes,  turns,  invert=True)
        )
        p.performance_score = round(score, 4)

    return profiles


# ---------------------------------------------------------------------------
# Stage 2 — Seating recommendation
# ---------------------------------------------------------------------------

@dataclass
class SeatingSuggestion:
    """A ranked server recommendation for a specific incoming reservation."""
    reservation:    Reservation
    server:         Server
    match_score:    float          # 0.0–1.0, higher = better fit
    reasoning:      list[str]      # Plain-English factors behind this score
    rank:           int = 0        # 1 = top recommendation


def _party_fit_score(profile: ServerProfile, party_size: int) -> float:
    """
    How well does this server's historical average party size match the incoming party?
    Servers who routinely handle similar party sizes are a better fit.
    """
    if profile.check_count == 0 or profile.total_covers == 0:
        return 0.5
    avg_covers = profile.total_covers / max(profile.check_count, 1)
    diff = abs(avg_covers - party_size)
    # Score degrades as the gap widens; cap at 4-cover difference = 0.0
    return max(0.0, 1.0 - (diff / 4.0))


def _floor_balance_score(profile: ServerProfile, all_profiles: list[ServerProfile]) -> float:
    """
    Prefer servers with fewer currently open covers.
    Normalizes open_covers across the active pool — lowest load scores highest.
    """
    loads = [p.open_covers for p in all_profiles]
    return _normalize(profile.open_covers, loads, invert=True)


def _vip_readiness_score(profile: ServerProfile, is_vip: bool) -> tuple[float, str | None]:
    """
    For VIP guests, prefer servers with high tip rates (guest satisfaction proxy).
    For non-VIP, this factor is neutral.
    """
    if not is_vip:
        return 0.5, None
    # Use tip rate as a proxy for high-touch service quality
    if profile.avg_tip_pct >= 22.0:
        return 1.0, "strong tip rate — well-suited for VIP guests"
    if profile.avg_tip_pct >= 18.0:
        return 0.6, None
    return 0.2, "lower tip rate — consider a higher-performing server for this VIP"


def recommend(
    reservation:  Reservation,
    profiles:     list[ServerProfile],
    weights:      ScoringWeights = DEFAULT_WEIGHTS,
    top_n:        int = 3,
) -> list[SeatingSuggestion]:
    """
    Score every available server against an incoming reservation.
    Returns top_n suggestions ranked best-first.
    """
    suggestions = []

    for profile in profiles:
        reasoning: list[str] = []
        score_parts: dict[str, float] = {}

        # --- Server performance ---
        score_parts["performance"] = profile.performance_score
        if profile.check_count == 0:
            reasoning.append("no checks yet this shift — neutral baseline")
        elif profile.performance_score >= 0.75:
            reasoning.append(f"strong shift performance ({profile.performance_score:.0%})")
        elif profile.performance_score <= 0.35:
            reasoning.append(f"below-average shift performance ({profile.performance_score:.0%})")

        # --- Floor balance ---
        balance = _floor_balance_score(profile, profiles)
        score_parts["balance"] = balance
        if profile.open_tables == 0:
            reasoning.append("no open tables — available")
        elif profile.open_tables >= 3:
            reasoning.append(f"carrying {profile.open_tables} open tables — heavy load")
        elif balance >= 0.75:
            reasoning.append("light floor load")

        # --- Party fit ---
        fit = _party_fit_score(profile, reservation.party_size)
        score_parts["fit"] = fit
        if profile.check_count > 0:
            avg = profile.total_covers / profile.check_count
            if fit >= 0.75:
                reasoning.append(
                    f"avg {avg:.1f} covers/table matches party of {reservation.party_size}"
                )
            elif fit <= 0.35:
                reasoning.append(
                    f"avg {avg:.1f} covers/table — unusual party size for this server"
                )

        # --- VIP readiness ---
        vip_score, vip_note = _vip_readiness_score(profile, reservation.is_vip)
        score_parts["vip"] = vip_score
        if vip_note:
            reasoning.append(vip_note)
        elif reservation.is_vip and profile.avg_tip_pct > 0:
            reasoning.append(f"tip rate {profile.avg_tip_pct:.1f}%")

        # --- Preference notes (informational, not scored) ---
        if reservation.preferences:
            pref_names = [p.value.replace("_", " ") for p in reservation.preferences]
            reasoning.append(f"guest preference: {', '.join(pref_names)}")

        # --- Composite match score ---
        match_score = (
            weights.server_performance * score_parts["performance"] +
            weights.floor_balance      * score_parts["balance"]     +
            weights.party_fit          * score_parts["fit"]         +
            weights.vip_readiness      * score_parts["vip"]
        )

        suggestions.append(SeatingSuggestion(
            reservation=reservation,
            server=profile.server,
            match_score=round(match_score, 4),
            reasoning=reasoning,
        ))

    # Sort best-first, assign ranks
    suggestions.sort(key=lambda s: s.match_score, reverse=True)
    for i, s in enumerate(suggestions[:top_n]):
        s.rank = i + 1

    return suggestions[:top_n]
