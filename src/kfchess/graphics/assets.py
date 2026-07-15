"""Assets: load the starting position and the piece sprites from ``assets/``.

This is the bridge from files on disk to the game core:

- :func:`load_board_csv` reads ``board.csv`` into a core :class:`Board`, reusing the
  same token vocabulary as the text layer (``wK``, ``bP``, ...).
- :class:`SpriteBank` loads and caches the piece sprites. Crucially, a piece's
  sprite folder is named by its **token** — exactly what :func:`piece_token` builds
  from a :class:`Piece` — so mapping a board piece to its images needs no lookup
  table, just string composition.

Only the graphics layer imports this; the text/VPL path is untouched.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

from kfchess.config import FPS_DEFAULT, STATE_IDLE
from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import PieceTypeRegistry, standard_piece_types
from kfchess.graphics.animation import Animation
from kfchess.graphics.img import Img

PathLike = Union[str, Path]


def piece_token(piece: Piece) -> str:
    """The token/folder name for a piece — a white king is ``"wK"``.

    This is the same composition the text printer uses, so a piece's token and its
    sprite folder name are guaranteed to agree.
    """
    return f"{piece.color.prefix}{piece.piece_type.letter}"


def token_to_piece(token: str, piece_types: PieceTypeRegistry) -> Optional[Piece]:
    """Turn a CSV cell token into a :class:`Piece`, or ``None`` for an empty cell.

    ``"wK"`` -> a white king; ``""`` (or whitespace) -> an empty cell. Reuses the
    core's own colour/type resolution, so an unknown token raises the same
    ``ValueError``/``KeyError`` the text parser would surface.
    """
    token = token.strip()
    if not token:
        return None
    color = Color.from_prefix(token[0])
    piece_type = piece_types.get(token[1:])
    return Piece(piece_type, color)


def load_board_csv(
    path: PathLike, piece_types: Optional[PieceTypeRegistry] = None
) -> Board:
    """Build a core :class:`Board` from a ``board.csv`` file.

    Each line is one board row of comma-separated cell tokens; an empty field is an
    empty cell. Truly blank lines (e.g. a trailing newline) are skipped, but a row of
    all-empty cells (``,,,,,,,``) is a real empty row and is kept.
    """
    piece_types = piece_types or standard_piece_types()
    grid = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip() and "," not in line:
            continue  # a genuinely blank line, not an empty board row
        row = [token_to_piece(cell, piece_types) for cell in line.split(",")]
        grid.append(row)
    return Board.from_grid(grid)


class AnimationBank:
    """Loads whole animations (frames + timing) on demand and caches them.

    Each ``(token, state)`` is loaded once — its ``config.json`` gives the frame rate
    and loop flag, and its ``sprites/`` folder gives the frames, scaled to ``cell_px``.
    Caching matters: the frame loop renders many times a second, so re-reading and
    re-scaling PNGs every frame would be wasteful.
    """

    def __init__(self, pieces_dir: PathLike, cell_px: int) -> None:
        self._pieces_dir = Path(pieces_dir)
        self._cell_px = cell_px
        self._cache: Dict[Tuple[str, str], Animation] = {}

    def animation(self, token: str, state: str = STATE_IDLE) -> Animation:
        """The :class:`Animation` for ``token`` in ``state`` (loaded once, then cached)."""
        key = (token, state)
        cached = self._cache.get(key)
        if cached is None:
            cached = self._load(token, state)
            self._cache[key] = cached
        return cached

    def _load(self, token: str, state: str) -> Animation:
        """Read a state's ``config.json`` and its numbered PNG frames into an Animation."""
        state_dir = self._pieces_dir / token / "states" / state
        config = json.loads((state_dir / "config.json").read_text(encoding="utf-8"))
        graphics = config.get("graphics", {})
        fps = graphics.get("frames_per_sec", FPS_DEFAULT)
        loop = graphics.get("is_loop", True)
        # Sort frames by their numeric filename (1.png, 2.png, ...), not lexically,
        # so 10.png would follow 9.png rather than 1.png.
        frame_paths = sorted(
            (state_dir / "sprites").glob("*.png"), key=lambda p: int(p.stem)
        )
        frames = [
            Img().read(path, size=(self._cell_px, self._cell_px))
            for path in frame_paths
        ]
        return Animation(frames, fps, loop)
