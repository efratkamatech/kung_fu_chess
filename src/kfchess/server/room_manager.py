"""RoomManager: hand out short ids for private rooms and map them to games.

A room is just a game you reach by a short shareable id (e.g. ``"7C2F"``) instead of by
matchmaking. This keeps the id bookkeeping in one small, pure place: it generates a
fresh, unused id for a new room and looks a room's game up by id. It knows nothing about
players, colours, or sockets — the :class:`~kfchess.server.lobby.Lobby` owns those and
seats joiners itself.

The id generator is injected (default: four uppercase hex characters) so tests can feed
a deterministic sequence, including a forced collision, with no randomness.
"""

from __future__ import annotations

import secrets
from typing import Callable, Dict, Optional


def _random_id() -> str:
    """A short, shareable room id: four uppercase hex characters, e.g. ``"7C2F"``."""
    return secrets.token_hex(2).upper()


class RoomManager:
    """Generates unique room ids and maps each to its game id."""

    def __init__(self, generate_id: Callable[[], str] = _random_id) -> None:
        self._generate_id = generate_id
        self._game_by_room: Dict[str, int] = {}

    def create(self, game_id: int) -> str:
        """Register ``game_id`` under a fresh room id (regenerating on a collision)."""
        room_id = self._generate_id()
        while room_id in self._game_by_room:
            room_id = self._generate_id()
        self._game_by_room[room_id] = game_id
        return room_id

    def game_for(self, room_id: str) -> Optional[int]:
        """The game id registered for ``room_id``, or ``None`` if there is no such room."""
        return self._game_by_room.get(room_id)

    def remove_game(self, game_id: int) -> None:
        """Forget the room (if any) that maps to ``game_id`` — called when it is over.

        A no-op for a matchmade game, which was never registered under a room id.
        """
        for room_id, mapped in list(self._game_by_room.items()):
            if mapped == game_id:
                del self._game_by_room[room_id]
