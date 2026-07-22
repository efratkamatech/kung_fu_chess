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

from typing import List, Optional

from kfchess.engine.arbiter import RealTimeArbiter
from kfchess.render_model import MovingPiece
from kfchess.engine.clock import Clock
from kfchess.engine.events import GameObserver
from kfchess.model.board import Board
from kfchess.model.piece import PieceState
from kfchess.model.position import Position
from kfchess.rules.rule_engine import RuleEngine


class GameEngine:
    """Validates moves, starts timed motions, and advances/resolves the clock."""

    __slots__ = ("_board", "_clock", "_rule_engine", "_arbiter", "_observers")

    def __init__(
        self,
        board: Board,
        clock: Clock,
        rule_engine: RuleEngine,
        arbiter: RealTimeArbiter,
        observers: Optional[List[GameObserver]] = None,
    ) -> None:
        self._board = board
        self._clock = clock
        self._rule_engine = rule_engine
        self._arbiter = arbiter
        # The same list the arbiter holds, so move-starts (emitted here) and captures
        # (emitted by the arbiter) reach the same observers. Empty on the text path.
        self._observers = observers if observers is not None else []

    def add_observer(self, observer: GameObserver) -> None:
        """Register an observer for game events (moves, captures, game over)."""
        self._observers.append(observer)

    @property
    def board(self) -> Board:
        """The current board state (read it to render or interpret clicks)."""
        return self._board

    @property
    def now_ms(self) -> int:
        """The current game time in ms — used to drive animation in sync with motion."""
        return self._clock.now_ms

    def moving_pieces(self) -> List[MovingPiece]:
        """Where each in-flight piece is *right now* (at the current clock time).

        A rendering aid: the board still shows a moving piece at its origin, while
        this reports its interpolated position between origin and destination.
        """
        return self._arbiter.moving_pieces(self._clock.now_ms)

    def cooldown_progress(self):
        """Each cooling piece mapped to its remaining cooldown fraction (for the gauge)."""
        return self._arbiter.cooldown_progress(self._clock.now_ms)

    @property
    def is_game_over(self) -> bool:
        """True once a king has been captured (the game has ended)."""
        return self._arbiter.is_game_over

    @property
    def winner(self):
        """The winning Color, or ``None`` while the game is still in progress."""
        return self._arbiter.winner

    def request_move(self, source: Position, target: Position) -> bool:
        """Start moving the piece at ``source`` to ``target`` if the move is legal.

        Returns ``True`` if a legal move was started, ``False`` if it was rejected
        (game over or an illegal move). A legal move begins a timed motion; the piece
        does not appear at the destination until enough time has passed.
        """
        if self._arbiter.is_game_over:
            return False
        if not self._rule_engine.is_legal_move(self._board, source, target):
            return False
        piece = self._board.piece_at(source)
        self._arbiter.start_motion(piece, source, target, self._clock.now_ms)
        for observer in self._observers:
            observer.on_move_started(piece, source, target)
        return True

    def legal_targets(self, source: Position) -> List[Position]:
        """Every cell the piece at ``source`` may legally move to right now.

        A rendering aid for highlighting moves; empty if the cell holds no piece or
        the piece cannot move (e.g. it is mid-move or on cooldown).
        """
        return [
            Position(row, col)
            for row in range(self._board.rows)
            for col in range(self._board.cols)
            if self._rule_engine.is_legal_move(self._board, source, Position(row, col))
        ]

    def request_jump(self, cell: Position) -> None:
        """Make the piece on ``cell`` jump in place, if it can.

        Ignored once the game is over, if the cell is empty, or if the piece is
        already moving (a moving piece cannot jump). ``cell`` is assumed on-board
        (the Controller checks bounds before calling).
        """
        if self._arbiter.is_game_over:
            return
        piece = self._board.piece_at(cell)
        if piece is None:
            return
        if piece.state is PieceState.MOVING:
            return
        self._arbiter.start_jump(piece, cell, self._clock.now_ms)

    def wait(self, ms: int) -> None:
        """Advance the clock by ``ms`` and resolve any motions that have arrived.

        Once the game is over the board is frozen, so waiting does nothing.
        """
        if self._arbiter.is_game_over:
            return
        self._clock.advance(ms)
        self._arbiter.resolve(self._clock.now_ms)
