"""Hud: draw the side panel — player names, score, and the recent moves log.

The HUD is pure output, like the board renderer: it reads the observers' accumulated
state (a :class:`ScoreBoard` and a :class:`MovesLog`) and writes text into the panel
region of the canvas (everything to the right of the board). It changes nothing.
"""

from __future__ import annotations

from kfchess.config import HUD_MOVES_VISIBLE, HUD_TEXT_COLOR
from kfchess.graphics.events import MovesLog, ScoreBoard
from kfchess.graphics.img import Img
from kfchess.model.color import Color


class Hud:
    """Renders the score/log panel to the right of the board."""

    def __init__(
        self,
        moves_log: MovesLog,
        score_board: ScoreBoard,
        white_name: str,
        black_name: str,
        board_px: int,
        moves_visible: int = HUD_MOVES_VISIBLE,
    ) -> None:
        self._moves_log = moves_log
        self._score = score_board
        self._white_name = white_name
        self._black_name = black_name
        self._left = board_px + 20  # left text margin inside the panel
        self._moves_visible = moves_visible

    def draw(self, canvas: Img) -> None:
        """Write the panel text onto ``canvas`` (in place)."""
        white_score = self._score.score(Color.WHITE)
        black_score = self._score.score(Color.BLACK)
        canvas.put_text(f"{self._white_name}: {white_score}", self._left, 50, 0.8, HUD_TEXT_COLOR, 2)
        canvas.put_text(f"{self._black_name}: {black_score}", self._left, 90, 0.8, HUD_TEXT_COLOR, 2)

        canvas.put_text("Moves", self._left, 150, 0.8, HUD_TEXT_COLOR, 2)
        y = 185
        for line in self._moves_log.recent(self._moves_visible):
            canvas.put_text(line, self._left, y, 0.6, HUD_TEXT_COLOR, 1)
            y += 30
