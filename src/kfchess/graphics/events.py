"""Concrete game observers for the graphics layer: the moves log and the scoreboard.

Both subclass the core :class:`GameObserver` and simply *listen*: the engine and
arbiter publish events, and these accumulate the state the HUD draws. They hold no
drawing code (that is the HUD's job) and no game logic — they only record what
happened.
"""

from __future__ import annotations

from typing import Dict, List

from kfchess.engine.events import GameObserver
from kfchess.graphics.assets import piece_token
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.position import Position


class MovesLog(GameObserver):
    """Records a human-readable line per move/capture, kept separately per side.

    A move is logged to the mover's side; a capture is logged to the *captor's* side
    (the victim's opponent), so each player's panel shows their own moves and kills.
    """

    def __init__(self, board_rows: int) -> None:
        # Board height, so a row index becomes a chess-style rank (bottom row = 1).
        self._board_rows = board_rows
        self._by_color: Dict[Color, List[str]] = {Color.WHITE: [], Color.BLACK: []}

    def on_move_started(
        self, piece: Piece, source: Position, target: Position
    ) -> None:
        self._by_color[piece.color].append(
            f"{piece_token(piece)} {self._square(source)} -> {self._square(target)}"
        )

    def on_capture(self, victim: Piece) -> None:
        self._by_color[victim.color.opponent].append(f"x {piece_token(victim)}")

    def recent(self, color: Color, count: int) -> List[str]:
        """The most recent ``count`` log lines for ``color`` (oldest first)."""
        return self._by_color[color][-count:]

    def _square(self, position: Position) -> str:
        """Chess-style square name, e.g. ``e2`` (file a.. from col, rank 1.. from bottom)."""
        file = chr(ord("a") + position.col)
        rank = self._board_rows - position.row
        return f"{file}{rank}"


class ScoreBoard(GameObserver):
    """Tallies, per side, the total material value captured by that side."""

    def __init__(self) -> None:
        self._score: Dict[Color, int] = {Color.WHITE: 0, Color.BLACK: 0}

    def on_capture(self, victim: Piece) -> None:
        # A capture is always by the enemy, so the victim's opponent earns its value.
        self._score[victim.color.opponent] += victim.piece_type.cost

    def score(self, color: Color) -> int:
        """The total captured value credited to ``color``."""
        return self._score[color]
