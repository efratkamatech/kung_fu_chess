"""GameObserver: the game's event interface (the Observer pattern).

The engine and arbiter *publish* game events — a move started, a piece captured, the
game ended — without knowing who listens. Observers *subscribe* to react: the moves
log records them, the scoreboard tallies captured material, and future observers (a
network spectator, a replay recorder) could join without touching the core.

This base class lives in the core (not the graphics layer) so the engine can emit
events without depending on anything above it. Its methods are no-ops, so an observer
overrides only the events it cares about.
"""

from __future__ import annotations

from kfchess.model.piece import Piece
from kfchess.model.position import Position


class GameObserver:
    """Base class for game-event listeners; override the events you care about."""

    def on_move_started(
        self, piece: Piece, source: Position, target: Position
    ) -> None:
        """A piece has begun moving from ``source`` toward ``target``."""

    def on_capture(self, victim: Piece) -> None:
        """``victim`` has just been captured and removed from the board."""

    def on_game_over(self) -> None:
        """A king has been captured; the game has ended."""
