"""GameSession: one game room on the server — the authoritative game plus its roles.

This is the server-side heart. It owns the live engine (built with the same
``build_game`` the text and windowed paths use), wires the bus and the
score/log/banner observers (reusing M1), hands out player colours, applies move
commands with an ownership check, advances time, and produces a :class:`GameSnapshot`
to send to every client.

It touches no sockets — the WebSocket server (step 2.5) drives it — so every branch of
its logic is unit-tested with no network at all.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from kfchess.app.bootstrap import build_game
from kfchess.bus import topics
from kfchess.bus.event_bus import EventBus
from kfchess.bus.events import GameStarted
from kfchess.bus.publisher import BusPublisher
from kfchess.config import (
    HUD_MOVES_VISIBLE,
    SOUND_CAPTURE,
    SOUND_GAME_OVER,
    SOUND_GAME_START,
    SOUND_MOVE,
)
from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import PieceState
from kfchess.model.position import Position
from kfchess.observers import GameBanner, MovesLog, ScoreBoard
from kfchess.server.command_parser import CommandError, parse_command
from kfchess.snapshot import CellView, GameSnapshot, MovingView
from kfchess.tokens import piece_token

# The first player to join is white, the second is black (slide 4).
_JOIN_ORDER = (Color.WHITE, Color.BLACK)

# Bus topic -> the sound-kind name a client's SoundEffects already knows how to play
# (config.SOUND_*, the same vocabulary graphics/sound.py uses locally). The server never
# plays a sound itself -- it only forwards *which* effect happened, over the immediate
# event channel, for whichever client is listening to render it.
_SOUND_KIND_BY_TOPIC = {
    topics.MOVE_STARTED: SOUND_MOVE,
    topics.CAPTURE: SOUND_CAPTURE,
    topics.GAME_STARTED: SOUND_GAME_START,
    topics.GAME_OVER: SOUND_GAME_OVER,
}


class GameSession:
    """One authoritative game: colour assignment, move handling, ticking, snapshots."""

    def __init__(self, board: Board) -> None:
        self._engine, _ = build_game(board)
        bus = EventBus()
        self._engine.add_observer(BusPublisher(bus))
        self._score = ScoreBoard()
        self._log = MovesLog(board.rows)
        self._banner = GameBanner()
        self._score.subscribe(bus)
        self._log.subscribe(bus)
        self._banner.subscribe(bus)
        self._pending_events: List[str] = []
        for topic, kind in _SOUND_KIND_BY_TOPIC.items():
            bus.subscribe(topic, self._make_collector(kind))
        bus.publish(GameStarted())
        self._taken: List[Color] = []
        self._names: Dict[Color, str] = {}
        self._ratings: Dict[Color, int] = {}

    def _make_collector(self, kind: str):
        """A bus handler that queues ``kind`` for the next :meth:`drain_events`."""
        return lambda event: self._pending_events.append(kind)

    def drain_events(self) -> List[str]:
        """The sound-kinds queued since the last call, clearing the queue.

        Read by the server after every command and tick, so each perception event is
        forwarded to clients exactly once.
        """
        events, self._pending_events = self._pending_events, []
        return events

    def assign_color(self) -> Optional[Color]:
        """Hand the next joining player a colour (white, then black); ``None`` if full."""
        if len(self._taken) >= len(_JOIN_ORDER):
            return None
        color = _JOIN_ORDER[len(self._taken)]
        self._taken.append(color)
        return color

    def set_name(self, color: Color, username: str) -> None:
        """Record ``username`` as the display name for ``color`` (from a Login message)."""
        self._names[color] = username

    def set_rating(self, color: Color, rating: int) -> None:
        """Record ``color``'s current ELO rating (for display in the snapshot)."""
        self._ratings[color] = rating

    def apply_command(self, color: Color, cmd: str) -> Optional[str]:
        """Apply a move command from ``color``.

        Returns ``None`` if the move was accepted, or a short reason string if it was
        refused (bad format, not your colour/piece, empty source, or illegal move).
        """
        try:
            move = parse_command(cmd, self._engine.board.rows, self._engine.board.cols)
        except CommandError as error:
            return str(error)
        if move.color is not color:
            return "not_your_colour"
        piece = self._engine.board.piece_at(move.source)
        if piece is None:
            return "empty_source"
        if piece.color is not color:
            return "not_your_piece"
        if piece.piece_type.letter != move.piece_letter:
            return "wrong_piece"
        if not self._engine.request_move(move.source, move.target):
            return "illegal_move"
        return None

    def tick(self, dt_ms: int) -> None:
        """Advance the game clock by ``dt_ms`` and resolve any arrivals."""
        self._engine.wait(dt_ms)

    def snapshot(self) -> GameSnapshot:
        """A serialisable picture of the game right now, ready to send to clients."""
        board = self._engine.board
        cooldowns = self._engine.cooldown_progress()
        cells = [
            [self._cell_view(row, col, cooldowns) for col in range(board.cols)]
            for row in range(board.rows)
        ]
        moving = [
            MovingView(piece_token(m.piece), m.position[0], m.position[1])
            for m in self._engine.moving_pieces()
        ]
        return GameSnapshot(
            rows=board.rows,
            cols=board.cols,
            cells=cells,
            moving=moving,
            scores={color: self._score.score(color) for color in _JOIN_ORDER},
            logs={
                color: self._log.recent(color, HUD_MOVES_VISIBLE)
                for color in _JOIN_ORDER
            },
            names=dict(self._names),  # only colours that have logged in so far
            ratings=dict(self._ratings),
            phase=self._banner.phase,
            winner=self._engine.winner,
            now_ms=self._engine.now_ms,
        )

    def _cell_view(
        self, row: int, col: int, cooldowns: Dict
    ) -> Optional[CellView]:
        """The view for one board cell, or ``None`` for empty / in-flight cells.

        A moving piece still sits on its origin in the board, but it is drawn from the
        ``moving`` overlay instead, so it is omitted from the settled cells here.
        """
        piece = self._engine.board.piece_at(Position(row, col))
        if piece is None or piece.state is PieceState.MOVING:
            return None
        return CellView(piece_token(piece), piece.state.name, cooldowns.get(piece, 0.0))
