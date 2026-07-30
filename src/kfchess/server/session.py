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
from kfchess.bus.events import GameOver, GameStarted
from kfchess.bus.publisher import BusPublisher
from kfchess.config import (
    HUD_MOVES_VISIBLE,
    RESIGN_COUNTDOWN_MS,
    SOUND_CAPTURE,
    SOUND_GAME_OVER,
    SOUND_GAME_START,
    SOUND_MOVE,
)
from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece, PieceState
from kfchess.model.position import Position
from kfchess.observers import GameBanner, MovesLog, ScoreBoard
from kfchess.server.command_parser import CommandError, parse_command
from kfchess.server.rating import updated_ratings
from kfchess.shared import protocol
from kfchess.shared.algebraic import position_to_square
from kfchess.shared.codes import RejectReason
from kfchess.shared.snapshot import CellView, GameSnapshot, MovingView
from kfchess.shared.tokens import piece_token

# The first player to join is white, the second is black (slide 4).
_JOIN_ORDER = (Color.WHITE, Color.BLACK)

# Bus topic -> the sound-kind name a client's SoundEffects already knows how to play
# (config.SOUND_*, the same vocabulary graphics/sound.py uses locally). The server never
# plays a sound itself -- it only forwards *which* effect happened, over the immediate
# event channel, for whichever client is listening to render it.
#
# Sound stays its own message rather than being derived on the client from the deltas
# below, because it is a *perception* concern with its own vocabulary: which effect a
# capture makes is this table's business, and duplicating the table on the far side to
# save thirty bytes would put it in two places.
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
        self._bus = EventBus()
        self._engine.add_observer(BusPublisher(self._bus))
        self._score = ScoreBoard()
        self._log = MovesLog(board.rows)
        self._banner = GameBanner()
        self._score.subscribe(self._bus)
        self._log.subscribe(self._bus)
        self._banner.subscribe(self._bus)
        # Everything the clients have not been told yet, in the order it happened: sound
        # events and deltas share one queue so a capture's sound never arrives after the
        # piece has already vanished from the board.
        self._pending: List[object] = []
        for topic, kind in _SOUND_KIND_BY_TOPIC.items():
            self._bus.subscribe(topic, self._make_collector(kind))
        self._bus.subscribe(topics.MOVE_STARTED, self._on_move_started)
        self._bus.subscribe(topics.SETTLED, self._on_settled)
        self._bus.subscribe(topics.CAPTURE, self._on_capture)
        self._bus.subscribe(topics.COOLDOWN_DONE, self._on_cooldown_done)
        self._bus.subscribe(topics.GAME_OVER, self._on_game_over)
        # The server's names for the pieces, handed out on first mention. A client
        # matches a delta to a piece by this number, so it must stay put for the piece's
        # whole life; the map dies with the session, which lasts a minute or two.
        self._piece_ids: Dict[Piece, int] = {}
        self._next_piece_id = 0
        self._bus.publish(GameStarted())
        self._taken: List[Color] = []
        self._names: Dict[Color, str] = {}
        self._ratings: Dict[Color, int] = {}
        # Disconnect handling (M5): the colour whose player has dropped and the ms left
        # on their auto-resign countdown; and a winner forced by a resign (which the
        # engine — pure, king-capture only — has no notion of).
        self._disconnected: Optional[Color] = None
        self._resign_ms = 0
        self._resigned_winner: Optional[Color] = None
        # The private-room id this game was opened under, or None for a matchmade game.
        self._room_id: Optional[str] = None

    def _make_collector(self, kind: str):
        """A bus handler that queues the sound ``kind`` for the next drain."""
        return lambda event: self._pending.append(protocol.Event(kind))

    def drain_deltas(self) -> List[object]:
        """The messages queued since the last call, in order, clearing the queue.

        This is what the lobby broadcasts: one message per thing that actually happened,
        instead of a fresh picture of the whole board twenty times a second. Read after
        every command and every tick, so each is forwarded to the clients exactly once.
        """
        pending, self._pending = self._pending, []
        return pending

    # --- turning game events into wire messages ------------------------------

    def _piece_id(self, piece: Piece) -> int:
        """This piece's wire name, assigned the first time it is mentioned."""
        piece_id = self._piece_ids.get(piece)
        if piece_id is None:
            piece_id = self._next_piece_id
            self._next_piece_id += 1
            self._piece_ids[piece] = piece_id
        return piece_id

    def _square(self, position: Position) -> str:
        """``position`` as the square players read, e.g. ``"e2"``."""
        return position_to_square(position, self._engine.board.rows)

    def _on_move_started(self, event) -> None:
        self._pending.append(
            protocol.MoveStarted(
                self._piece_id(event.piece),
                piece_token(event.piece),
                self._square(event.source),
                self._square(event.target),
                event.start_ms,
                event.arrival_ms,
            )
        )

    def _on_settled(self, event) -> None:
        self._pending.append(
            protocol.Settled(
                self._piece_id(event.piece),
                piece_token(event.piece),  # what it became, if it promoted on landing
                self._square(event.cell),
                event.at_ms,
                event.cooldown_ms,
            )
        )

    def _on_capture(self, event) -> None:
        self._pending.append(
            protocol.Captured(
                self._piece_id(event.victim), piece_token(event.victim), event.at_ms
            )
        )

    def _on_cooldown_done(self, event) -> None:
        self._pending.append(
            protocol.CooldownDone(self._piece_id(event.piece), event.at_ms)
        )

    def _on_game_over(self, event) -> None:
        self._pending.append(
            protocol.GameOver(
                event.winner, self._engine.now_ms, self._final_ratings(event.winner)
            )
        )

    def _final_ratings(self, winner: Optional[Color]) -> Dict[Color, int]:
        """Both players' new ELO, or ``{}`` if this game does not count.

        Computed here, the instant the game ends, rather than waited for from the
        database: :func:`updated_ratings` is pure and both current ratings are already
        held, so the player sees her new number in the same message that tells her she
        won. The store applies the identical arithmetic to the identical inputs when it
        persists the result, so the two never disagree.

        Empty for a game with an unfilled seat — a room whose creator captured an
        unowned king — which is the same game the lobby declines to rate.
        """
        if winner is None or len(self._ratings) < len(_JOIN_ORDER):
            return {}
        loser = winner.opponent
        new_winner, new_loser = updated_ratings(
            self._ratings[winner], self._ratings[loser]
        )
        return {winner: new_winner, loser: new_loser}

    def assign_color(self) -> Optional[Color]:
        """Hand the next joining player a colour (white, then black); ``None`` if full."""
        if len(self._taken) >= len(_JOIN_ORDER):
            return None #check it
        color = _JOIN_ORDER[len(self._taken)]
        self._taken.append(color)
        return color

    def set_name(self, color: Color, username: str) -> None:
        """Record ``username`` as the display name for ``color`` (from a Login message)."""
        self._names[color] = username

    def set_rating(self, color: Color, rating: int) -> None:
        """Record ``color``'s current ELO rating (for display in the snapshot)."""
        self._ratings[color] = rating

    def set_room_id(self, room_id: str) -> None:
        """Mark this game as belonging to a private room (its id rides the snapshot)."""
        self._room_id = room_id

    @property
    def winner(self) -> Optional[Color]:
        """The side that won, by a king capture *or* a resign; ``None`` while playing."""
        return self._resigned_winner or self._engine.winner

    def is_over(self) -> bool:
        """Whether the game has ended, by a king capture *or* a resign."""
        return self.winner is not None

    def mark_disconnected(self, color: Color) -> None:
        """Note that ``color``'s player has dropped; start their auto-resign countdown.

        Does nothing once the game is over. The countdown (and which colour is missing)
        travels in the snapshot so the opponent's screen can show it; :meth:`tick` runs
        it down and resigns the missing player at zero.
        """
        if self.is_over():
            return
        self._disconnected = color
        self._resign_ms = RESIGN_COUNTDOWN_MS
        # The deadline, once, instead of a countdown re-sent in every snapshot: the
        # opponent's screen counts down to it against its own clock.
        self._pending.append(
            protocol.Disconnected(color, self._engine.now_ms + RESIGN_COUNTDOWN_MS)
        )

    def resign(self, loser: Color) -> None:
        """End the game with ``loser``'s opponent as the winner (no king was captured).

        Publishes ``GameOver`` on the bus — the same event a capture raises — so the
        banner flips to "over" and the game-over sound fires, exactly as a normal win.
        """
        if self.is_over():
            return
        self._resigned_winner = loser.opponent
        self._disconnected = None
        self._resign_ms = 0
        self._bus.publish(GameOver(winner=self._resigned_winner))

    def reconnect(self) -> None:
        """A disconnected player has returned; cancel the pending resign countdown."""
        self._disconnected = None
        self._resign_ms = 0
        self._pending.append(protocol.Reconnected())

    def disconnected_color(self) -> Optional[Color]:
        """The colour whose player has dropped and is mid-countdown, or ``None``."""
        return self._disconnected

    def name_of(self, color: Color) -> Optional[str]:
        """The logged-in name recorded for ``color``, or ``None`` if that seat is empty."""
        return self._names.get(color)

    def apply_command(self, color: Color, cmd: str) -> Optional[RejectReason]:
        """Apply a move command from ``color``.

        Returns ``None`` if the move was accepted, or the :class:`RejectReason` it was
        refused for (game already over, unparseable command, not your colour/piece,
        empty source, or illegal move).
        """
        if self.is_over():
            return RejectReason.GAME_OVER
        try:
            move = parse_command(cmd, self._engine.board.rows, self._engine.board.cols)
        except CommandError:
            # The parser's specific complaint is dropped: the Lobby logs the rejected
            # command alongside this code, which is enough to diagnose one.
            return RejectReason.BAD_COMMAND
        if move.color is not color:
            return RejectReason.NOT_YOUR_COLOUR
        piece = self._engine.board.piece_at(move.source)
        if piece is None:
            return RejectReason.EMPTY_SOURCE
        if piece.color is not color:
            return RejectReason.NOT_YOUR_PIECE
        if piece.piece_type.letter != move.piece_letter:
            return RejectReason.WRONG_PIECE
        if not self._engine.request_move(move.source, move.target):
            return RejectReason.ILLEGAL_MOVE
        return None

    def next_event_delay_ms(self) -> Optional[int]:
        """How long from now until this game needs ticking, or ``None`` if nothing is due.

        A delay rather than a moment, because every game keeps its own clock starting at
        zero — two games' absolute times are not comparable, their waits are. Both kinds
        of scheduled thing count: what the board owes (a piece arriving, a cooldown
        ending) and what the seat owes (a missing player's auto-resign).
        """
        if self.is_over():
            return None
        delays = []
        due_ms = self._engine.next_event_ms()
        if due_ms is not None:
            delays.append(max(0, due_ms - self._engine.now_ms))
        if self._disconnected is not None:
            delays.append(max(0, self._resign_ms))
        return min(delays) if delays else None

    def tick(self, dt_ms: int) -> None:
        """Advance the game clock by ``dt_ms``, resolve arrivals, run any resign timer."""
        if self._disconnected is not None and not self.is_over():
            self._resign_ms -= dt_ms
            if self._resign_ms <= 0:
                self.resign(self._disconnected)
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
            MovingView(
                piece_token(m.piece),
                m.position[0],
                m.position[1],
                self._piece_id(m.piece),
            )
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
            winner=self.winner,
            now_ms=self._engine.now_ms,
            disconnected=self._disconnected,
            resign_ms=max(self._resign_ms, 0) if self._disconnected is not None else 0,
            room_id=self._room_id,
        )

    def _cell_view(
        self, row: int, col: int, cooldowns: Dict
    ) -> Optional[CellView]:
        """The view for one board cell, or ``None`` for empty / in-flight cells.

        A moving piece still sits on its origin in the board, but it is drawn from the
        ``moving`` overlay instead, so it is omitted from the settled cells here.

        Each cell carries the piece's wire name as well, so that a client meeting a piece
        for the first time in a snapshot can still recognise the delta that captures it
        later — a pawn that never moves is otherwise never named at all.
        """
        piece = self._engine.board.piece_at(Position(row, col))
        if piece is None or piece.state is PieceState.MOVING:
            return None #check it
        return CellView(
            piece_token(piece),
            piece.state.name,
            cooldowns.get(piece, 0.0),
            self._piece_id(piece),
        )
