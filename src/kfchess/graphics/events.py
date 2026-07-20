"""Concrete bus subscribers for the graphics layer: the moves log and the scoreboard.

Both *listen on the EventBus*: the engine and arbiter publish game events (through the
:class:`BusPublisher` adapter), and these two accumulate the state the HUD draws. They
hold no drawing code (that is the HUD's job) and no game logic — they only record what
happened, in response to bus events.

Each exposes ``subscribe(bus)`` to register its own handlers on the topics it cares
about, so the wiring in bootstrap is a single call per subscriber.
"""

from __future__ import annotations

from typing import Dict, List

from kfchess.bus import topics
from kfchess.bus.event_bus import EventBus
from kfchess.graphics.assets import piece_token
from kfchess.model.color import Color
from kfchess.model.position import Position


class MovesLog:
    """Records a human-readable line per move/capture, kept separately per side.

    A move is logged to the mover's side; a capture is logged to the *captor's* side
    (the victim's opponent), so each player's panel shows their own moves and kills.
    """

    def __init__(self, board_rows: int) -> None:
        # Board height, so a row index becomes a chess-style rank (bottom row = 1).
        self._board_rows = board_rows
        self._by_color: Dict[Color, List[str]] = {Color.WHITE: [], Color.BLACK: []}

    def subscribe(self, bus: EventBus) -> None:
        """Listen for move-starts and captures on ``bus``."""
        bus.subscribe(topics.MOVE_STARTED, self._on_move)
        bus.subscribe(topics.CAPTURE, self._on_capture)

    def _on_move(self, event) -> None:
        self._by_color[event.piece.color].append(
            f"{piece_token(event.piece)} "
            f"{self._square(event.source)} -> {self._square(event.target)}"
        )

    def _on_capture(self, event) -> None:
        self._by_color[event.victim.color.opponent].append(
            f"x {piece_token(event.victim)}"
        )

    def recent(self, color: Color, count: int) -> List[str]:
        """The most recent ``count`` log lines for ``color`` (oldest first)."""
        return self._by_color[color][-count:]

    def _square(self, position: Position) -> str:
        """Chess-style square name, e.g. ``e2`` (file a.. from col, rank 1.. from bottom)."""
        file = chr(ord("a") + position.col)
        rank = self._board_rows - position.row
        return f"{file}{rank}"


class ScoreBoard:
    """Tallies, per side, the total material value captured by that side."""

    def __init__(self) -> None:
        self._score: Dict[Color, int] = {Color.WHITE: 0, Color.BLACK: 0}

    def subscribe(self, bus: EventBus) -> None:
        """Listen for captures on ``bus``."""
        bus.subscribe(topics.CAPTURE, self._on_capture)

    def _on_capture(self, event) -> None:
        # A capture is always by the enemy, so the victim's opponent earns its value.
        self._score[event.victim.color.opponent] += event.victim.piece_type.cost

    def score(self, color: Color) -> int:
        """The total captured value credited to ``color``."""
        return self._score[color]
