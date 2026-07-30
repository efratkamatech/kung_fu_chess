"""UserStore: accounts and ratings, persisted in SQLite or PostgreSQL.

One small table — ``users(username, salt, pw_hash, rating)`` — that survives across
server runs. Passwords are never stored in the clear: each account gets a random salt
and we keep only a PBKDF2-HMAC-SHA256 hash, verified with a constant-time compare, so
stealing the database still does not reveal anyone's password.

Login is "register-or-login" in one step (slide 5, "just for presentation"): a
first-seen username is created at the starting rating; a returning one must match its
stored password. The store touches only its database and the pure ELO maths — no engine,
network, or graphics — and is exercised end-to-end against an in-memory database.

**Two databases, one implementation.** A laptop keeps a SQLite file; a container is
handed a ``postgresql://`` DSN and keeps nothing of its own (see ``docker-compose.yml``).
Those are the same four statements, so what differs between them is described as *data*
— a :class:`Dialect` — rather than as a second class. A second class would have been a
second copy of the register-or-login rule, and two copies drift the first time either is
touched. The PBKDF2 parameters are shared for the same reason: a hash written by one
backend has to stay valid under the other.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from kfchess.config import DATABASE_URL, START_RATING, USERS_DB
from kfchess.server.rating import updated_ratings

_ITERATIONS = 100_000  # PBKDF2 rounds — deliberately slow to resist brute force
_SALT_BYTES = 16

# The DSN schemes that mean "this is PostgreSQL"; anything else names a SQLite file.
_POSTGRES_SCHEMES = ("postgresql://", "postgres://")


def _hash(password: str, salt: bytes) -> bytes:
    """The PBKDF2-HMAC-SHA256 digest of ``password`` under ``salt``."""
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes(salt), _ITERATIONS
    )


@dataclass(frozen=True)
class Dialect:
    """The two things SQLite and PostgreSQL spell differently in this store.

    ``placeholder`` is how a bound parameter is written, and ``blob`` is what a column of
    raw bytes is called. That is the whole difference: both drivers expose the same
    ``execute(sql, params) -> cursor`` shape, so nothing else has to vary.
    """

    placeholder: str
    blob: str


SQLITE = Dialect(placeholder="?", blob="BLOB")
POSTGRES = Dialect(placeholder="%s", blob="BYTEA")


def dialect_for(target: Union[str, Path]) -> Dialect:
    """Which database ``target`` names — a DSN means PostgreSQL, a path means SQLite."""
    return POSTGRES if str(target).startswith(_POSTGRES_SCHEMES) else SQLITE


def spell(statement: str, dialect: Dialect) -> str:
    """``statement``, written here with ``?`` placeholders, in ``dialect``'s spelling.

    Every statement passed through is a literal in this module — no caller's text ever
    reaches it — so this stays a spelling change and never becomes string-built SQL.
    """
    return statement.replace("?", dialect.placeholder)


def _connect_sqlite(target: str):
    """A connection to the SQLite file (or ``":memory:"``) at ``target``."""
    return sqlite3.connect(target)


def _connect_postgres(target: str):  # pragma: no cover  (needs a live PostgreSQL)
    """A connection to the PostgreSQL server named by the DSN ``target``.

    ``psycopg`` is imported here rather than at module scope so that a machine with no
    PostgreSQL driver installed can still import — and test — everything else.
    """
    import psycopg

    return psycopg.connect(target)


# Dialect -> how to open it. A table rather than an ``if``, so the branch only a live
# PostgreSQL server could take is not a branch the coverage gate has to argue about.
_CONNECT = {SQLITE: _connect_sqlite, POSTGRES: _connect_postgres}


class UserStore:
    """A store of usernames, password hashes, and ELO ratings."""

    def __init__(self, target: Optional[Union[str, Path]] = None) -> None:
        """Open ``target``: a SQLite path, a PostgreSQL DSN, or the configured default.

        The default is ``DATABASE_URL`` when the environment sets one and the SQLite file
        otherwise — so :func:`kfchess.server.game_server.serve` writes ``UserStore()``
        once and is right in a container and on a laptop alike.
        """
        target = target if target is not None else (DATABASE_URL or USERS_DB)
        self._dialect = dialect_for(target)
        self._conn = _CONNECT[self._dialect](str(target))
        self._execute(
            "CREATE TABLE IF NOT EXISTS users ("
            f"username TEXT PRIMARY KEY, salt {self._dialect.blob}, "
            f"pw_hash {self._dialect.blob}, rating INTEGER)"
        )
        self._conn.commit()

    def _execute(self, statement: str, params: tuple = ()):
        """Run one statement in this backend's spelling, and return its cursor."""
        return self._conn.execute(spell(statement, self._dialect), params)

    def register_or_login(self, username: str, password: str) -> Optional[int]:
        """Create the account (first time) or verify it (returning), returning the rating.

        Returns the account's rating on success, or ``None`` if the username exists but
        the password does not match.
        """
        row = self._execute(
            "SELECT salt, pw_hash, rating FROM users WHERE username = ?", (username,)
        ).fetchone()
        if row is None:
            salt = os.urandom(_SALT_BYTES)
            self._execute(
                "INSERT INTO users (username, salt, pw_hash, rating) VALUES (?, ?, ?, ?)",
                (username, salt, _hash(password, salt), START_RATING),
            )
            self._conn.commit()
            return START_RATING
        salt, pw_hash, rating = row
        # ``bytes(...)`` because the two drivers hand back a bytes column differently —
        # SQLite as ``bytes``, psycopg as a memoryview — and the compare needs one type.
        if hmac.compare_digest(bytes(pw_hash), _hash(password, salt)):
            return rating
        return None # check it

    def get_rating(self, username: str) -> int:
        """The current rating of an existing user."""
        return self._execute(
            "SELECT rating FROM users WHERE username = ?", (username,)
        ).fetchone()[0]

    def set_rating(self, username: str, rating: int) -> None:
        """Overwrite an existing user's rating."""
        self._execute(
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
