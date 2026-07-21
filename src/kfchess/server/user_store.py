"""UserStore: accounts and ratings, persisted in a SQLite file on the server.

One small table — ``users(username, salt, pw_hash, rating)`` — that survives across
server runs. Passwords are never stored in the clear: each account gets a random salt
and we keep only a PBKDF2-HMAC-SHA256 hash, verified with a constant-time compare, so
stealing the database still does not reveal anyone's password.

Login is "register-or-login" in one step (slide 5, "just for presentation"): a
first-seen username is created at the starting rating; a returning one must match its
stored password. The store touches only SQLite and the pure ELO maths — no engine,
network, or graphics — and is exercised end-to-end against an in-memory database.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
from typing import Optional, Union
from pathlib import Path

from kfchess.config import START_RATING, USERS_DB
from kfchess.server.rating import updated_ratings

_ITERATIONS = 100_000  # PBKDF2 rounds — deliberately slow to resist brute force
_SALT_BYTES = 16


def _hash(password: str, salt: bytes) -> bytes:
    """The PBKDF2-HMAC-SHA256 digest of ``password`` under ``salt``."""
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)


class UserStore:
    """A SQLite-backed store of usernames, password hashes, and ELO ratings."""

    def __init__(self, db_path: Union[str, Path] = USERS_DB) -> None:
        self._conn = sqlite3.connect(str(db_path))
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS users ("
            "username TEXT PRIMARY KEY, salt BLOB, pw_hash BLOB, rating INTEGER)"
        )
        self._conn.commit()

    def register_or_login(self, username: str, password: str) -> Optional[int]:
        """Create the account (first time) or verify it (returning), returning the rating.

        Returns the account's rating on success, or ``None`` if the username exists but
        the password does not match.
        """
        row = self._conn.execute(
            "SELECT salt, pw_hash, rating FROM users WHERE username = ?", (username,)
        ).fetchone()
        if row is None:
            salt = os.urandom(_SALT_BYTES)
            self._conn.execute(
                "INSERT INTO users (username, salt, pw_hash, rating) VALUES (?, ?, ?, ?)",
                (username, salt, _hash(password, salt), START_RATING),
            )
            self._conn.commit()
            return START_RATING
        salt, pw_hash, rating = row
        if hmac.compare_digest(pw_hash, _hash(password, salt)):
            return rating
        return None

    def get_rating(self, username: str) -> int:
        """The current rating of an existing user."""
        return self._conn.execute(
            "SELECT rating FROM users WHERE username = ?", (username,)
        ).fetchone()[0]

    def set_rating(self, username: str, rating: int) -> None:
        """Overwrite an existing user's rating."""
        self._conn.execute(
            "UPDATE users SET rating = ? WHERE username = ?", (rating, username)
        )
        self._conn.commit()

    def record_win(self, winner: str, loser: str) -> None:
        """Apply an ELO update for a finished game and persist both new ratings."""
        new_winner, new_loser = updated_ratings(
            self.get_rating(winner), self.get_rating(loser)
        )
        self.set_rating(winner, new_winner)
        self.set_rating(loser, new_loser)

    def close(self) -> None:
        """Close the underlying database connection."""
        self._conn.close()
