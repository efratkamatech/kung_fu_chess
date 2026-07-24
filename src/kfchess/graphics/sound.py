"""Sound: play a short sound effect in reaction to bus events.

The bus announces game events; :class:`SoundEffects` subscribes and asks a
:class:`SoundPlayer` to play the matching effect. The player is *injected*, so *how*
to make noise (a real beep, or silence) is decided separately from *when* (the events).

:class:`SoundPlayer` is silent by default — the same no-op-base convention as
``GameObserver`` — so tests and the text path make no sound. The windowed launcher
injects a :class:`WinsoundPlayer`, which beeps via the Windows ``winsound`` module and
so needs no audio-asset files. ``winsound`` is imported lazily, inside the one method
that beeps, so this module (and the silent default player) still import on non-Windows
systems — the game simply runs without sound there.
"""

from __future__ import annotations

from kfchess.bus import topics
from kfchess.bus.event_bus import EventBus
from kfchess.config import (
    SOUND_CAPTURE,
    SOUND_GAME_OVER,
    SOUND_GAME_START,
    SOUND_MOVE,
    WINSOUND_TONES,
)


class SoundPlayer:
    """Plays a named sound effect. The base is silent (the default player)."""

    def play(self, sound: str) -> None:
        """Play ``sound`` — a no-op here, so the default player is silent."""


class WinsoundPlayer(SoundPlayer):
    """A real player: a short beep per effect via the Windows ``winsound`` module."""

    def play(self, sound: str) -> None:  # pragma: no cover  (irreducible audio I/O)
        import winsound  # Windows-only; imported here so the module loads anywhere

        frequency, duration_ms = WINSOUND_TONES[sound]
        winsound.Beep(frequency, duration_ms)


class SoundEffects:
    """Subscribes to game events and asks its player to play the matching effect."""

    def __init__(self, player: SoundPlayer) -> None:
        self._player = player

    def subscribe(self, bus: EventBus) -> None:
        """React to move/capture/start/over events by playing their effect."""
        bus.subscribe(topics.MOVE_STARTED, lambda event: self._player.play(SOUND_MOVE))
        bus.subscribe(topics.CAPTURE, lambda event: self._player.play(SOUND_CAPTURE))
        bus.subscribe(
            topics.GAME_STARTED, lambda event: self._player.play(SOUND_GAME_START)
        )
        bus.subscribe(
            topics.GAME_OVER, lambda event: self._player.play(SOUND_GAME_OVER)
        )
