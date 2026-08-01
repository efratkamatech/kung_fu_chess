"""The shared matchmaker: one queue for everybody, however many shards there are.

**The pairing rules do not change.** A seeker is paired with the waiting player whose
rating is closest within :data:`~kfchess.config.MATCH_ELO_RANGE`, ties go to whoever has
waited longest, and the earlier arrival plays white. What changes is where the queue lives
and how it is searched — and it has to change, because a queue in one process's memory
means one queue *per process*, and ten thousand shards would be ten thousand separate
pools where a player in one could never meet a player in another.

The queue is a ranking scored by rating, so the ELO window is a score range:

    mm:waiting  ->  { "{joined_ms}:{username}": rating }

Two things about that are worth stating plainly, because the obvious version of each is
wrong.

**The search asks for one member, not for the window.** Fetching everyone within ±100 and
picking the closest is O(how many are in the window), and in a busy pool that is most of
the queue — the linear scan this replaced, moved onto the network. Asking for the nearest
*above* and the nearest *below* is two queries, each O(log n), and the closest of those
two is the closest overall.

**Nobody sweeps the queue for expired waiters.** Counting down every waiter's clock on a
timer is O(everyone waiting), twenty times a second, which was the more expensive half of
the old implementation. Instead a waiter who has been there too long is dropped by
whoever next trips over her, and a client that has not been matched gives up on its own
clock. Each dead entry is removed once, by a query that was going to read it anyway.

Rating buckets — splitting this into ``mm:bucket:1200``, ``mm:bucket:1250`` and so on —
are deliberately **not** here. They would not make the search faster: it is already
logarithmic, and log of a million is twenty. What they buy is splitting one large key
across a Redis cluster, and what they cost is five times the queries on every seek, since
a ±100 window straddles up to five 50-point buckets. That is a trade to make when a
measurement says the key is hot, not before.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional

from kfchess.config import MATCH_ELO_RANGE, MATCH_TIMEOUT_MS

# The one ranking every seeker is in. A name, not a pattern: there is exactly one queue.
QUEUE = "mm:waiting"
# Which member is which, and what proves a seeker is still there.
_JOINED_DIGITS = 13  # milliseconds since the epoch, to the year 2286
_SEPARATOR = ":"
# How much longer a seeker's own record lives than her patience — see :meth:`_add`.
_SEEKER_TTL_FACTOR = 2


def wall_clock_ms() -> int:
    """The time of day in milliseconds — shared, so two shards agree who waited longer."""
    return time.time_ns() // 1_000_000


@dataclass(frozen=True)
class Match:
    """Two paired seekers, by name. ``white`` was already waiting; ``black`` just sought.

    Named rather than numbered: a client id means something only inside the process that
    issued it, and the whole point of this queue is that the two players may be about to
    be seated by a shard that has met neither of them.

    Both ratings travel with them for the same reason. The shard that ends up running the
    game may never have spoken to either player, and it has to put a number beside each
    name on the board; going back to the database for something the queue was already
    sorted by would be a round trip to learn what we just read.
    """

    white: str
    black: str
    white_rating: int = 0
    black_rating: int = 0


@dataclass(frozen=True)
class Waiter:
    """One player in the queue, as read back out of it."""

    username: str
    rating: int
    joined_ms: int

    @property
    def member(self) -> str:
        """How this waiter is written in the ranking."""
        return f"{self.joined_ms:0{_JOINED_DIGITS}d}{_SEPARATOR}{self.username}"

    @classmethod
    def from_member(cls, member: str, score: float) -> "Waiter":
        joined_ms, username = member.split(_SEPARATOR, 1)
        return cls(username, int(score), int(joined_ms))


class Matchmaker:
    """Pairs seekers across every shard, out of one shared queue."""

    def __init__(
        self,
        store,
        elo_range: int = MATCH_ELO_RANGE,
        timeout_ms: int = MATCH_TIMEOUT_MS,
        now_ms: Callable[[], int] = wall_clock_ms,
    ) -> None:
        self._store = store
        self._elo_range = elo_range
        self._timeout_ms = timeout_ms
        self._now_ms = now_ms

    def seek(self, username: str, rating: int) -> Optional[Match]:
        """Pair ``username`` with the closest waiting seeker in range, else enqueue her.

        Returns the :class:`Match` if one was made — the
        partner is taken out of the queue, and plays white for having arrived first — or
        ``None``, in which case she is now waiting.
        """
        partner = self._closest_waiting(username, rating)
        if partner is not None:
            self._remove(partner)
            return Match(partner.username, username, partner.rating, rating)
        # Whatever this player left in the queue last time goes first. She may have given
        # up waiting and come back: her old entry is still in the ranking (nothing sweeps
        # it), and a player listed twice under two arrival times is one somebody can be
        # paired with at an address she is no longer answering.
        self.cancel(username)
        self._add(Waiter(username, rating, self._now_ms()))
        return None

    def cancel(self, username: str) -> None:
        """Take a seeker out of the queue — she dropped, or went to open a room instead.

        A no-op if she is not in it. This is what keeps the queue from pairing somebody
        with a player who left: the lazy expiry below is the floor under it, not a
        substitute for it.
        """
        waiter = self._waiting(username)
        if waiter is not None:
            self._remove(waiter)

    def is_waiting(self, username: str) -> bool:
        """Whether ``username`` is still *actively* waiting for a game.

        A player past the give-up point is not: her client has stopped listening and
        offered her the menu again, so pressing Play must start a fresh search rather
        than be ignored as a duplicate. She is still in the ranking until somebody trips
        over her, and :meth:`seek` clears that entry before adding the new one.
        """
        waiter = self._waiting(username)
        return waiter is not None and not self._has_given_up(waiter)

    # --- the search -----------------------------------------------------------

    def _closest_waiting(self, username: str, rating: int) -> Optional[Waiter]:
        """The nearest suitable waiter, dropping any found to have given up.

        Loops only to skip what it evicts, and each eviction removes a member for good,
        so it cannot spin.
        """
        while True:
            candidates = [
                waiter
                for waiter in (self._nearest_above(rating), self._nearest_below(rating))
                if waiter is not None and waiter.username != username
            ]
            expired = [waiter for waiter in candidates if self._has_given_up(waiter)]
            if expired:
                for waiter in expired:
                    self._remove(waiter)
                continue
            if not candidates:
                return None
            # Closest rating wins; an exact tie goes to whoever has waited longest, which
            # is the same rule the single-process queue applied by insertion order.
            return min(
                candidates, key=lambda w: (abs(w.rating - rating), w.joined_ms)
            )

    def _nearest_above(self, rating: int) -> Optional[Waiter]:
        return self._read(rating, rating + self._elo_range, reverse=False)

    def _nearest_below(self, rating: int) -> Optional[Waiter]:
        return self._read(rating - self._elo_range, rating, reverse=True)

    def _read(self, low: int, high: int, reverse: bool) -> Optional[Waiter]:
        found = self._store.first_in_range(QUEUE, low, high, reverse=reverse)
        return None if found is None else Waiter.from_member(*found)

    def _has_given_up(self, waiter: Waiter) -> bool:
        """Whether this waiter has been there longer than anyone would still be waiting."""
        return self._now_ms() - waiter.joined_ms >= self._timeout_ms

    # --- the queue itself -----------------------------------------------------

    def _add(self, waiter: Waiter) -> None:
        self._store.add_to_ranking(QUEUE, waiter.member, waiter.rating)
        # A second key, so that cancelling and "am I waiting?" are one lookup by name.
        # The ranking cannot answer those: it is indexed by rating, not by who.
        #
        # It deliberately outlives the give-up point, rather than expiring with it. This
        # is the only record of *where* in the ranking a player is, and the ranking entry
        # can outlive the give-up point too — so letting this expire first would strand
        # one, findable by nobody and removable by nobody but the next passing search.
        self._store.set(
            _seeker_key(waiter.username),
            f"{waiter.joined_ms}{_SEPARATOR}{waiter.rating}",
            ttl_s=_SEEKER_TTL_FACTOR * self._timeout_ms // 1000,
        )

    def _remove(self, waiter: Waiter) -> None:
        self._store.remove_from_ranking(QUEUE, waiter.member)
        self._store.delete(_seeker_key(waiter.username))

    def _waiting(self, username: str) -> Optional[Waiter]:
        stored = self._store.get(_seeker_key(username))
        if stored is None:
            return None
        joined_ms, rating = stored.split(_SEPARATOR)
        return Waiter(username, int(rating), int(joined_ms))


def _seeker_key(username: str) -> str:
    """Where one seeker's own record lives. One place, so nothing spells it differently."""
    return f"mm:seeker:{username}"
