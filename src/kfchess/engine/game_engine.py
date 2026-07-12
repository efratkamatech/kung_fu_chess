"""GameEngine: owns the board and clock, and performs game actions.

It is the single writer to the board. ``request_move`` now validates the move with
the injected RuleEngine and applies it only if legal; ``wait`` advances the clock.

Still absent for now (added at this same seam later):
- movement over time (Iteration 6) — a move currently completes instantly;
- captures bookkeeping / game-over (Iterations 4, 9).

The engine knows the board, clock, and rules, but not pixels, clicks, or the text
format (those belong to the Controller and Text I/O layers).
"""

from __future__ import annotations

from kfchess.engine.clock import Clock
from kfchess.model.board import Board
from kfchess.model.position import Position
from kfchess.rules.rule_engine import RuleEngine


class GameEngine:
    """Validates and applies moves to the board; advances the clock on wait."""

    __slots__ = ("_board", "_clock", "_rule_engine")

    def __init__(self, board: Board, clock: Clock, rule_engine: RuleEngine) -> None:
        self._board = board
        self._clock = clock
        self._rule_engine = rule_engine

    @property
    def board(self) -> Board:
        """The current board state (read it to render or interpret clicks)."""
        return self._board

    def request_move(self, source: Position, target: Position) -> None:
        """Move the piece at ``source`` to ``target`` if the move is legal.

        Illegal moves are ignored (the piece stays put). Because legality already
        confirms a piece is at ``source``, the removal below always finds one.
        """
        if not self._rule_engine.is_legal_move(self._board, source, target):
            return
        piece = self._board.remove(source)
        self._board.place(target, piece)

    def wait(self, ms: int) -> None:
        """Advance the game clock by ``ms`` milliseconds."""
        self._clock.advance(ms)
