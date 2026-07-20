"""GameSnapshot: a plain, serialisable picture of the game at one instant.

This is the state the server sends to every client and the renderer draws from — the
"same snapshot Transport serializes remotely" from the architecture doc. It holds only
primitive and model values (tokens, state names, numbers, colours) and no engine,
graphics, or network objects, so it survives a round-trip to JSON and back unchanged.

It is *built* on the server from the live game (step 2.4) and *rebuilt* into drawable
state on the client (step 2.7); here we define the data and its JSON form. It lives at
the package root — not under ``engine`` — because it is shared by the server and the
client and also carries score/log values, which are not engine concepts. It imports
only :class:`Color`, so it stays free of every layer above the model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from kfchess.model.color import Color


@dataclass(frozen=True)
class CellView:
    """One settled piece on the board: its token, lifecycle state, and cooldown."""

    token: str            # the piece token, e.g. "wK"
    state: str            # a PieceState name: "IDLE" / "COOLDOWN" / "JUMPING"
    cooldown: float = 0.0  # remaining cooldown fraction (1.0 -> 0.0); only for COOLDOWN


@dataclass(frozen=True)
class MovingView:
    """One in-flight piece: its token and current *fractional* (row, col)."""

    token: str
    row: float
    col: float


@dataclass(frozen=True)
class GameSnapshot:
    """The whole game at one instant, ready to serialise and draw."""

    rows: int
    cols: int
    cells: List[List[Optional[CellView]]]  # cells[row][col] -> a piece view or None
    moving: List[MovingView]
    scores: Dict[Color, int]
    logs: Dict[Color, List[str]]
    phase: str                             # "start" / "playing" / "over"
    winner: Optional[Color]
    now_ms: int

    def to_dict(self) -> dict:
        """A JSON-ready dict; colours become their one-letter prefix (``w`` / ``b``)."""
        return {
            "rows": self.rows,
            "cols": self.cols,
            "cells": [
                [
                    None
                    if cell is None
                    else {
                        "token": cell.token,
                        "state": cell.state,
                        "cooldown": cell.cooldown,
                    }
                    for cell in row
                ]
                for row in self.cells
            ],
            "moving": [
                {"token": m.token, "row": m.row, "col": m.col} for m in self.moving
            ],
            "scores": {color.value: value for color, value in self.scores.items()},
            "logs": {color.value: lines for color, lines in self.logs.items()},
            "phase": self.phase,
            "winner": None if self.winner is None else self.winner.value,
            "now_ms": self.now_ms,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GameSnapshot":
        """Rebuild a snapshot from its :meth:`to_dict` form."""
        cells = [
            [
                None
                if cell is None
                else CellView(cell["token"], cell["state"], cell["cooldown"])
                for cell in row
            ]
            for row in data["cells"]
        ]
        moving = [MovingView(m["token"], m["row"], m["col"]) for m in data["moving"]]
        scores = {Color(prefix): value for prefix, value in data["scores"].items()}
        logs = {Color(prefix): lines for prefix, lines in data["logs"].items()}
        winner = None if data["winner"] is None else Color(data["winner"])
        return cls(
            rows=data["rows"],
            cols=data["cols"],
            cells=cells,
            moving=moving,
            scores=scores,
            logs=logs,
            phase=data["phase"],
            winner=winner,
            now_ms=data["now_ms"],
        )
