"""Hud: draw one player's panel — their name, score, and their moves log.

Two Huds are used, one per side of the board (white on one side, black on the other).
Each is pure output: it reads its player's accumulated state (from a shared
:class:`ScoreBoard` and :class:`MovesLog`) and writes text at its own x on the canvas.

The name is a fixed label for the local game, but the networked client passes an
optional ``name_source`` (anything with ``name(color)``) so the HUD can show the
username a player logged in with — falling back to the fixed label until it arrives.
"""

from __future__ import annotations

from kfchess.config import HUD_MOVES_VISIBLE, HUD_TEXT_COLOR
from kfchess.graphics.img import Img
from kfchess.model.color import Color
from kfchess.observers import MovesLog, ScoreBoard


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
        name_source=None,
    ) -> None:
        self._name = player_name
        self._color = color
        self._moves_log = moves_log
        self._score = score_board
        self._left = left_x
        self._moves_visible = moves_visible
        self._name_source = name_source  # optional: overrides player_name when it has one

    def _display_name(self) -> str:
        """The name to show: the logged-in username if there is one, else the default."""
        if self._name_source is not None:
            return self._name_source.name(self._color) or self._name
        return self._name

    def draw(self, canvas: Img) -> None:
        """Write this player's panel onto ``canvas`` (in place)."""
        score = self._score.score(self._color)
        canvas.put_text(
            f"{self._display_name()}: {score}", self._left, 50, 0.8, HUD_TEXT_COLOR, 2
        )
        canvas.put_text("Moves", self._left, 110, 0.8, HUD_TEXT_COLOR, 2)
        y = 145
        for line in self._moves_log.recent(self._color, self._moves_visible):
            canvas.put_text(line, self._left, y, 0.6, HUD_TEXT_COLOR, 1)
            y += 30
