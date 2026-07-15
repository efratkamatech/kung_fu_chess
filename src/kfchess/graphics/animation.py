"""Animation: a sequence of sprite frames played at a fixed frame rate.

An :class:`Animation` knows nothing about the game or time source — you hand it *how
long* the current state has been running (``elapsed_ms``) and it returns which frame to
show. That keeps it pure and easy to test without a screen. Two playback modes:

- ``loop=True`` (e.g. idle): the frames cycle forever.
- ``loop=False`` (e.g. jump, rest): the frames play once and then hold on the last
  one until the state changes.
"""

from __future__ import annotations

from typing import List

from kfchess.graphics.img import Img


class Animation:
    """A fixed sequence of frames shown at ``fps``, looping or holding the last frame."""

    __slots__ = ("_frames", "_fps", "_loop")

    def __init__(self, frames: List[Img], fps: float, loop: bool) -> None:
        if not frames:
            raise ValueError("an animation needs at least one frame")
        self._frames = frames
        self._fps = fps
        self._loop = loop

    @property
    def frame_count(self) -> int:
        """How many frames this animation has."""
        return len(self._frames)

    @property
    def duration_ms(self) -> int:
        """How long one full play-through takes, in milliseconds (0 if ``fps`` is 0)."""
        if self._fps <= 0:
            return 0
        return int(len(self._frames) / self._fps * 1000)

    def frame_at(self, elapsed_ms: int) -> Img:
        """The frame to show ``elapsed_ms`` after this state began.

        The index advances by ``fps`` frames per second; a looping animation wraps
        around, a non-looping one clamps to (holds) the final frame.
        """
        if self._fps <= 0:
            return self._frames[0]
        index = int(elapsed_ms * self._fps / 1000)
        if index < 0:
            index = 0
        count = len(self._frames)
        if self._loop:
            index %= count
        else:
            index = min(index, count - 1)
        return self._frames[index]
