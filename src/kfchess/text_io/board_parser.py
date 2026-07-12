"""BoardParser: turn fixture text into a Board plus the list of command lines.

This is part of the Text I/O layer. It owns knowledge of the *text format* — the
``Board:`` / ``Commands:`` section headers and the cell tokens — and it validates
that both required sections are present. It does **not** execute commands or judge
whether a command is known: a command is only "unknown" at execution time, so that
check lives with the command executor. The parser just hands back the raw command
lines for the executor to interpret.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from kfchess.config import (
    BOARD_SECTION_HEADER,
    COMMANDS_SECTION_HEADER,
    EMPTY_CELL,
    ERR_INVALID_PIECE,
    ERR_MISSING_BOARD_SECTION,
    ERR_MISSING_COMMANDS_SECTION,
)
from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import PieceTypeRegistry


class FixtureError(Exception):
    """A malformed fixture. ``code`` is the verbatim error token to print."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ParsedFixture:
    """The result of parsing a fixture: a built Board and the raw command lines."""

    board: Board
    commands: list[str]


class BoardParser:
    """Parses the two-section fixture text. The piece-type registry is injected so
    the set of recognized pieces is configurable (and swappable in tests)."""

    def __init__(self, piece_types: PieceTypeRegistry) -> None:
        self._piece_types = piece_types

    def parse(self, text: str) -> ParsedFixture:
        lines = text.splitlines()

        board_idx = self._find_header(lines, BOARD_SECTION_HEADER)
        if board_idx is None:
            raise FixtureError(ERR_MISSING_BOARD_SECTION)
        commands_idx = self._find_header(lines, COMMANDS_SECTION_HEADER)
        if commands_idx is None:
            raise FixtureError(ERR_MISSING_COMMANDS_SECTION)

        board_lines = lines[board_idx + 1 : commands_idx]
        command_lines = lines[commands_idx + 1 :]

        board = self._parse_board(board_lines)
        commands = [line.strip() for line in command_lines if line.strip()]
        return ParsedFixture(board=board, commands=commands)

    @staticmethod
    def _find_header(lines: list[str], header: str) -> Optional[int]:
        """Index of the line whose trimmed text equals ``header``, else ``None``."""
        for index, line in enumerate(lines):
            if line.strip() == header:
                return index
        return None

    def _parse_board(self, board_lines: list[str]) -> Board:
        grid: list[list[Optional[Piece]]] = []
        for line in board_lines:
            if not line.strip():
                continue  # skip blank lines (e.g. a stray trailing newline)
            row = [self._parse_cell(token) for token in line.split()]
            grid.append(row)
        return Board.from_grid(grid)

    def _parse_cell(self, token: str) -> Optional[Piece]:
        """A single cell token -> a Piece, or None for the empty-cell marker.

        A malformed token (bad color prefix or unknown piece letter) is converted
        into a FixtureError so the program prints an error code instead of crashing.
        """
        if token == EMPTY_CELL:
            return None
        try:
            color = Color.from_prefix(token[0])
            piece_type = self._piece_types.get(token[1:])
        except (ValueError, KeyError):
            raise FixtureError(ERR_INVALID_PIECE) from None
        return Piece(piece_type, color)
