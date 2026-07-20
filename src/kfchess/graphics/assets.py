"""Assets: load the starting position and the piece sprites from ``assets/``.

This is the bridge from files on disk to the game core:

- :class:`AnimationBank` loads and caches the piece sprites. Crucially, a piece's
  sprite folder is named by its **token** — exactly what
  :func:`kfchess.tokens.piece_token` builds from a :class:`Piece` — so mapping a board
  piece to its images needs no lookup table, just string composition.

The token vocabulary and the CSV board loader live in :mod:`kfchess.tokens` so the
headless server can share them; only the sprite loading below is graphics-specific.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Tuple, Union

from kfchess.config import FPS_DEFAULT, STATE_IDLE
from kfchess.graphics.animation import Animation
from kfchess.graphics.img import Img

PathLike = Union[str, Path]


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
