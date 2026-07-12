"""GameEngine: owns the board and clock, and performs game actions.

It is the single writer to the board. For Iteration 2 an action is minimal:
``request_move`` relocates a piece immediately, and ``wait`` advances the clock.
Deliberately absent for now (added in later iterations at this same seam):
- legality checks (Iteration 3, via a RuleEngine) — right now any move is applied;
- movement over time (Iteration 6) — right now a move completes instantly;
- captures/promotion/game-over — later.

The engine knows about the board, clock, and positions, but not about pixels,
clicks, or the text format (those belong to the Controller and Text I/O layers).
"""

from __future__ import annotations

from kfchess.engine.clock import Clock
from kfchess.model.board import Board
from kfchess.model.position import Position


class GameEngine:
    """Applies moves to the board and advances the clock on wait."""

    __slots__ = ("_board", "_clock")

    def __init__(self, board: Board, clock: Clock) -> None:
        self._board = board
        self._clock = clock

    @property
    def board(self) -> Board:
        """The current board state (read it to render or interpret clicks)."""
        return self._board

    def request_move(self, source: Position, target: Position) -> None:
        """Move the piece at ``source`` to ``target``.

        Iteration 2: immediate and unconditional (no rules yet). If ``source`` has
        no piece, nothing happens.
        """
        piece = self._board.remove(source)
        if piece is not None:
            self._board.place(target, piece)

    def wait(self, ms: int) -> None:
        """Advance the game clock by ``ms`` milliseconds."""
        self._clock.advance(ms)
