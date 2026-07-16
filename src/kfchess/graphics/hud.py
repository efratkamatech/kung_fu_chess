"""Hud: draw one player's panel — their name, score, and their moves log.

Two Huds are used, one per side of the board (white on one side, black on the other).
Each is pure output: it reads its player's accumulated state (from a shared
:class:`ScoreBoard` and :class:`MovesLog`) and writes text at its own x on the canvas.
"""

from __future__ import annotations

from kfchess.config import HUD_MOVES_VISIBLE, HUD_TEXT_COLOR
from kfchess.graphics.events import MovesLog, ScoreBoard
from kfchess.graphics.img import Img
from kfchess.model.color import Color


class Hud:
    """Renders one player's name/score/moves panel at a fixed left x on the canvas."""

    def __init__(
        self,
        player_name: str,
        color: Color,
        moves_log: MovesLog,
        score_board: ScoreBoard,
        left_x: int,
        moves_visible: int = HUD_MOVES_VISIBLE,
    ) -> None:
        self._name = player_name
        self._color = color
        self._moves_log = moves_log
        self._score = score_board
        self._left = left_x
        self._moves_visible = moves_visible

    def draw(self, canvas: Img) -> None:
        """Write this player's panel onto ``canvas`` (in place)."""
        score = self._score.score(self._color)
        canvas.put_text(f"{self._name}: {score}", self._left, 50, 0.8, HUD_TEXT_COLOR, 2)
        canvas.put_text("Moves", self._left, 110, 0.8, HUD_TEXT_COLOR, 2)
        y = 145
        for line in self._moves_log.recent(self._color, self._moves_visible):
            canvas.put_text(line, self._left, y, 0.6, HUD_TEXT_COLOR, 1)
            y += 30
