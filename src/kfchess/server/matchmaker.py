"""Matchmaker: a waiting queue that pairs players of similar skill (slide 6).

When a logged-in player presses "Play", they *seek* a game. If someone of a close
rating is already waiting, the two are paired immediately; otherwise the seeker joins
the queue and waits. A lone waiter is not left forever: each :meth:`tick` advances the
waiters' clocks, and after :data:`MATCH_TIMEOUT_MS` the client is told no opponent was
found.

This is pure bookkeeping — it knows nothing about sockets, colours, or the engine, only
integer client ids and ratings — so every branch is unit-tested with no network and no
real time (the timeout rides the same ``tick(dt_ms)`` the rest of the server already
uses, exactly like the engine's simulated :class:`~kfchess.engine.clock.Clock`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from kfchess.config import MATCH_ELO_RANGE, MATCH_TIMEOUT_MS


@dataclass(frozen=True)
class Match:
    """Two paired seekers. ``white`` was already waiting; ``black`` just sought.

    Giving the earlier arrival white mirrors the "first to join is white" rule used
    everywhere else; the lobby turns a match into a real :class:`GameSession`.
    """

    white: int
    black: int


class Matchmaker:
    """A rating-aware waiting queue: pair close seekers, time lone ones out."""

    def __init__(
        self,
        elo_range: int = MATCH_ELO_RANGE,
        timeout_ms: int = MATCH_TIMEOUT_MS,
    ) -> None:
        self._elo_range = elo_range
        self._timeout_ms = timeout_ms
        self._rating: Dict[int, int] = {}     # waiting client id -> its rating
        self._waited_ms: Dict[int, int] = {}  # waiting client id -> ms waited so far

    def seek(self, client_id: int, rating: int) -> Optional[Match]:
        """Pair ``client_id`` with the closest waiting seeker in range, else enqueue.

        Returns the :class:`Match` if one was made (the partner is removed from the
        queue), or ``None`` if nobody suitable was waiting — in which case the seeker
        is now queued and will either be matched by a later :meth:`seek` or time out.
        """
        partner = self._closest_in_range(rating)
        if partner is not None:
            self._remove(partner)
            return Match(white=partner, black=client_id)
        self._rating[client_id] = rating
        self._waited_ms[client_id] = 0
        return None

    def _closest_in_range(self, rating: int) -> Optional[int]:
        """The waiting client whose rating is nearest ``rating`` within the window.

        Ties (equal distance) go to whoever has been waiting longer — the earliest
        insertion, which dict iteration preserves — so nobody is starved.
        """
        best: Optional[int] = None
        best_diff: Optional[int] = None
        for client_id, other in self._rating.items():
            diff = abs(other - rating)
            if diff <= self._elo_range and (best_diff is None or diff < best_diff):
                best, best_diff = client_id, diff
        return best

    def tick(self, dt_ms: int) -> List[int]:
        """Advance every waiter's clock by ``dt_ms``; return those that just timed out.

        Timed-out clients are removed from the queue, so the caller can notify each one
        exactly once ("can't find opponent").
        """
        timed_out: List[int] = []
        for client_id in list(self._rating):
            self._waited_ms[client_id] += dt_ms
            if self._waited_ms[client_id] >= self._timeout_ms:
                timed_out.append(client_id)
                self._remove(client_id)
        return timed_out

    def cancel(self, client_id: int) -> None:
        """Drop a waiting seeker (e.g. on disconnect); a no-op if not queued."""
        self._remove(client_id)

    def is_waiting(self, client_id: int) -> bool:
        """Whether ``client_id`` is currently in the queue."""
        return client_id in self._rating

    def _remove(self, client_id: int) -> None:
        self._rating.pop(client_id, None)
        self._waited_ms.pop(client_id, None)
