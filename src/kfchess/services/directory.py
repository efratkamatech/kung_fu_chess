"""The player directory: where each player is sitting, and the proof that it is her.

``player:{username} -> {room_id, shard_id, color, seat_token}``, with a short life.

It replaces a linear scan. Finding a returning player's seat used to mean walking every
game on the server and asking each one whether the missing player was this one — fine for
the two games a laptop runs, and impossible at the five million this design is sized for,
where the seat is not even on the machine doing the asking. A lookup by name answers in
one step, from anywhere.

**And it closes a real hole.** Reconnect was identified by *username alone*: anyone who
knew your name could take your seat by logging in as you. A username is a claim, not
proof. So a seat carries a :attr:`Seat.seat_token` — random, minted by the shard when it
seats you, handed back to you, and demanded when you return.

Who does what with it is the part worth being careful about, and it is deliberately not
symmetric:

- the **shard** mints the token and is the only thing that verifies it, because it issued
  it and it owns the room the seat is in;
- **Auth** reads this directory on the login path and hands the seat back to the player,
  so returning costs no extra round trip;
- the **WS Gateway** never touches either. It is handed a room to follow and forwards a
  token it cannot read. A gateway that checked tokens would be a security decision point
  in a component that exists to be replicated and thrown away.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from typing import Callable, Optional

from kfchess.config import PLAYER_TTL_S, SEAT_TOKEN_BYTES
from kfchess.model.color import Color


def mint_token() -> str:
    """A fresh seat token. ``secrets`` because a guessable one proves nothing."""
    return secrets.token_hex(SEAT_TOKEN_BYTES)


@dataclass(frozen=True)
class Seat:
    """Where one player is sitting, and what proves she may sit back down there."""

    room_id: str
    shard_id: str
    color: Color
    seat_token: str

    def to_dict(self) -> dict:
        return {
            "room_id": self.room_id,
            "shard_id": self.shard_id,
            "color": self.color.value,
            "seat_token": self.seat_token,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Seat":
        return cls(
            data["room_id"],
            data["shard_id"],
            Color(data["color"]),
            data["seat_token"],
        )


class PlayerDirectory:
    """Records which room each player is in, for as long as that is worth knowing."""

    def __init__(
        self,
        store,
        ttl_s: int = PLAYER_TTL_S,
        new_token: Callable[[], str] = mint_token,
    ) -> None:
        self._store = store
        self._ttl_s = ttl_s
        self._new_token = new_token

    def take_seat(self, username: str, room_id: str, shard_id: str, color: Color) -> Seat:
        """Record that ``username`` now holds ``color`` in ``room_id``, and mint her token.

        Returns the whole seat, token included, because the caller is the shard that just
        seated her: it has to keep the token to check it later, and to send it to her so
        she has something to come back with.
        """
        seat = Seat(room_id, shard_id, color, self._new_token())
        self._store.set(_key(username), json.dumps(seat.to_dict()), ttl_s=self._ttl_s)
        return seat

    def seat_of(self, username: str) -> Optional[Seat]:
        """Where ``username`` is sitting, or ``None`` — one lookup, not a search."""
        stored = self._store.get(_key(username))
        return None if stored is None else Seat.from_dict(json.loads(stored))

    def leave(self, username: str) -> None:
        """Forget where ``username`` was sitting — her game ended, or she gave the seat up.

        Not strictly required: every entry expires on its own, which is what covers the
        shard that crashes without tidying. This is for the ordinary case, so that a
        player whose game just finished is not told to reconnect to it.
        """
        self._store.delete(_key(username))


def _key(username: str) -> str:
    """The directory key for one player. One place, so nothing can spell it differently."""
    return f"player:{username}"
