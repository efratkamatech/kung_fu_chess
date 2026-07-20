"""ClientController: client-side selection that turns clicks into move commands.

In the server-authoritative model the client runs no engine, so this is much simpler
than the core Controller: it only tracks which of *your own* pieces is selected (read
from the latest snapshot) and, on the next click, composes the ``WQe2e5`` command to
send — it never mutates a board. A spectator (no colour) can select nothing.

It works in board cells; mapping a pixel to a cell is the mouse layer's job. The
returned string is the command the caller hands to :meth:`NetClient.queue_command`.
"""

from __future__ import annotations

from typing import Optional

from kfchess.algebraic import build_command
from kfchess.model.color import Color
from kfchess.model.position import Position
from kfchess.snapshot import GameSnapshot


class ClientController:
    """Holds the selected cell and turns a follow-up click into a move command."""

    def __init__(self, color: Optional[Color]) -> None:
        self._color = color  # this client's colour, or None for a spectator
        self._selected: Optional[Position] = None
        self._selected_token: Optional[str] = None

    @property
    def selected(self) -> Optional[Position]:
        """The currently selected cell, or ``None`` — the renderer outlines it."""
        return self._selected

    def click(self, cell: Position, snapshot: GameSnapshot) -> Optional[str]:
        """Interpret a click on ``cell`` against ``snapshot``; return a command or None.

        Nothing selected: clicking your own piece selects it. Something selected:
        clicking another of your pieces switches the selection; clicking any other cell
        builds the move command and clears the selection. Off-board clicks and
        spectators do nothing.
        """
        if self._color is None or not self._in_bounds(cell, snapshot):
            return None
        # Drop a stale selection: the selected piece may have moved or been captured
        # since we picked it, so the selected cell no longer holds our token.
        if (
            self._selected is not None
            and self._token_at(snapshot, self._selected) != self._selected_token
        ):
            self._clear()

        token = self._token_at(snapshot, cell)
        mine = token is not None and token[0] == self._color.prefix
        if self._selected is None:
            if mine:
                self._select(cell, token)
            return None
        if mine:
            self._select(cell, token)  # switch to the newly clicked friendly piece
            return None
        command = build_command(
            self._color, self._selected_token[1:], self._selected, cell, snapshot.rows
        )
        self._clear()
        return command

    @staticmethod
    def _in_bounds(cell: Position, snapshot: GameSnapshot) -> bool:
        return 0 <= cell.row < snapshot.rows and 0 <= cell.col < snapshot.cols

    @staticmethod
    def _token_at(snapshot: GameSnapshot, cell: Position) -> Optional[str]:
        view = snapshot.cells[cell.row][cell.col]
        return view.token if view is not None else None

    def _select(self, cell: Position, token: str) -> None:
        self._selected = cell
        self._selected_token = token

    def _clear(self) -> None:
        self._selected = None
        self._selected_token = None
