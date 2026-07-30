"""RoomManager: hand out short ids for private rooms and map them to games.

A room is just a game you reach by a short shareable id (e.g. ``"7C2FQK"``) instead of by
matchmaking. This keeps the id bookkeeping in one small, pure place: it generates a
fresh, unused id for a new room and looks a room's game up by id. It knows nothing about
players, colours, or sockets — the :class:`~kfchess.server.lobby.Lobby` owns those and
seats joiners itself.

The two maps are kept in step deliberately: ``room -> game`` answers a joiner, and
``game -> room`` lets a finished game forget its id without walking every room on the
server. The id generator is injected (default: :func:`random_id`) so tests can feed a
deterministic sequence, including a forced collision, with no randomness.
"""

from __future__ import annotations

import secrets
from typing import Callable, Dict, Optional

from kfchess.config import ROOM_ID_ALPHABET, ROOM_ID_LENGTH, ROOM_ID_MAX_ATTEMPTS


class RoomIdUnavailable(RuntimeError):
    """No free room id turned up within :data:`~kfchess.config.ROOM_ID_MAX_ATTEMPTS`."""


def random_id() -> str:
    """A short, shareable room id from the unambiguous alphabet, e.g. ``"7C2FQK"``.

    ``secrets`` rather than ``random``, because a guessable id is an open door into
    somebody else's game.
    """
    return "".join(secrets.choice(ROOM_ID_ALPHABET) for _ in range(ROOM_ID_LENGTH))


class RoomManager:
    """Generates unique room ids and maps each to its game id."""

    def __init__(self, generate_id: Callable[[], str] = random_id) -> None:
        self._generate_id = generate_id
        self._game_by_room: Dict[str, int] = {}
        self._room_by_game: Dict[int, str] = {}

    def create(self, game_id: int) -> str:
        """Register ``game_id`` under a fresh room id, redrawing on a collision.

        Raises :class:`RoomIdUnavailable` after
        :data:`~kfchess.config.ROOM_ID_MAX_ATTEMPTS` tries. The bound is the whole point:
        this used to redraw until it found a free id, and the thread it would have spun
        on for ever is the one thread that runs every game on the server.
        """
        for _ in range(ROOM_ID_MAX_ATTEMPTS):
            room_id = self._generate_id()
            if room_id not in self._game_by_room:
                self._game_by_room[room_id] = game_id
                self._room_by_game[game_id] = room_id
                return room_id
        raise RoomIdUnavailable(f"no free room id in {ROOM_ID_MAX_ATTEMPTS} attempts")

    def game_for(self, room_id: str) -> Optional[int]:
        """The game id registered for ``room_id``, or ``None`` if there is no such room."""
        return self._game_by_room.get(room_id)

    def remove_game(self, game_id: int) -> None:
        """Forget the room (if any) that maps to ``game_id`` — called when it is over.

        A no-op for a matchmade game, which was never registered under a room id. Both
        directions go together, so neither map can outlive the other.
        """
        room_id = self._room_by_game.pop(game_id, None)
        if room_id is not None:
            del self._game_by_room[room_id]
