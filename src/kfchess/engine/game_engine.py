"""GameEngine: coordinates the board, clock, rules, and the real-time arbiter.

A move now takes time. ``request_move`` validates with the RuleEngine and, if
legal, hands the move to the arbiter as a *motion* — the piece stays at its origin,
marked MOVING, until it arrives. ``wait`` advances the clock and asks the arbiter to
resolve any motions that have now arrived.

The engine no longer mutates the board directly; the arbiter applies a move when it
completes. The engine knows the board, clock, rules, and arbiter, but not pixels,
clicks, or the text format (those belong to the Controller and Text I/O layers).
"""

from __future__ import annotations

from kfchess.engine.arbiter import RealTimeArbiter
from kfchess.engine.clock import Clock
from kfchess.model.board import Board
from kfchess.model.position import Position
from kfchess.rules.rule_engine import RuleEngine


class GameEngine:
    """Validates moves, starts timed motions, and advances/resolves the clock."""

    __slots__ = ("_board", "_clock", "_rule_engine", "_arbiter")

    def __init__(
        self,
        board: Board,
        clock: Clock,
        rule_engine: RuleEngine,
        arbiter: RealTimeArbiter,
    ) -> None:
        self._board = board
        self._clock = clock
        self._rule_engine = rule_engine
        self._arbiter = arbiter

    @property
    def board(self) -> Board:
        """The current board state (read it to render or interpret clicks)."""
        return self._board

    def request_move(self, source: Position, target: Position) -> None:
        """Start moving the piece at ``source`` to ``target`` if the move is legal.

        Illegal moves are ignored. Legal ones begin a timed motion; the piece does
        not appear at the destination until enough time has passed.
        """
        if self._arbiter.is_game_over:
            return  # the game has ended; ignore further moves
        if not self._rule_engine.is_legal_move(self._board, source, target):
            return
        piece = self._board.piece_at(source)
        self._arbiter.start_motion(piece, source, target, self._clock.now_ms)

    def wait(self, ms: int) -> None:
        """Advance the clock by ``ms`` and resolve any motions that have arrived.

        Once the game is over the board is frozen, so waiting does nothing.
        """
        if self._arbiter.is_game_over:
            return
        self._clock.advance(ms)
        self._arbiter.resolve(self._clock.now_ms)
