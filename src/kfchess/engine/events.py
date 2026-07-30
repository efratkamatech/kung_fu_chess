"""GameObserver: the game's event interface (the Observer pattern).

The engine and arbiter *publish* game events — a move started, a piece captured, the
game ended — without knowing who listens. Observers *subscribe* to react: the moves
log records them, the scoreboard tallies captured material, and future observers (a
network spectator, a replay recorder) could join without touching the core.

This base class lives in the core (not the graphics layer) so the engine can emit
events without depending on anything above it. Its methods are no-ops, so an observer
overrides only the events it cares about.

Every event is stamped with the game time it happened at, and a motion announces where
and when it will end as well as where it began. That is not for the core's own benefit —
nothing here reads it back — but for the observer that puts these events on a wire: a
client told "this piece left e2 for e5 at 1000 and lands at 4000" can draw every frame
in between without being sent the board again. The times are the arbiter's *true* ones,
not the tick they happened to be noticed on, so a remote listener sees the same timeline
the engine resolved against.
"""

from __future__ import annotations

from typing import Optional

from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.position import Position


class GameObserver:
    """Base class for game-event listeners; override the events you care about."""

    def on_move_started(
        self,
        piece: Piece,
        source: Position,
        target: Position,
        start_ms: int,
        arrival_ms: int,
    ) -> None:
        """``piece`` has left ``source`` for ``target``, due to land at ``arrival_ms``."""

    def on_settled(
        self, piece: Piece, cell: Position, at_ms: int, cooldown_ms: int
    ) -> None:
        """``piece`` came to rest on ``cell`` and is on cooldown for ``cooldown_ms``.

        Raised however a motion ends — arriving, stopping short of a friend, or landing
        from a jump — and after any promotion, so ``piece`` is already what it became.
        """

    def on_capture(self, victim: Piece, at_ms: int) -> None:
        """``victim`` has just been captured and removed from the board."""

    def on_cooldown_done(self, piece: Piece, at_ms: int) -> None:
        """``piece``'s landing cooldown has elapsed; it is free to move again."""

    def on_game_over(self, winner: Optional[Color]) -> None:
        """A king has been captured; the game has ended and ``winner`` took it."""
