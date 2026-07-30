"""The same account behaviour, against a real PostgreSQL server.

Skipped unless ``DATABASE_URL`` points at one, so a laptop and CI stay green without a
database. With `docker compose up -d postgres` running, this is how to run it::

    DATABASE_URL=postgresql://kfchess:kfchess@localhost:5432/kfchess pytest tests/integration

What it is really checking is the handful of things a unit test on SQLite cannot: that
the statements are spelled in a dialect PostgreSQL accepts, that a ``BYTEA`` column comes
back as something the constant-time compare will take, and that ``psycopg`` is installed
and connects. The behaviour itself is the same code either way — that is the point of
:class:`~kfchess.server.user_store.Dialect` — so this deliberately does not restate every
rule the unit tests already cover.
"""

import os
import secrets

import pytest

from kfchess.config import START_RATING
from kfchess.server.user_store import POSTGRES, UserStore, dialect_for

DATABASE_URL = os.environ.get("DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL.startswith(("postgresql://", "postgres://")),
    reason="set DATABASE_URL to a postgresql:// DSN to run the PostgreSQL tests",
)


@pytest.fixture
def store():
    """A store on the configured server, and a promise to leave no rows behind."""
    store = UserStore(DATABASE_URL)
    created = []
    yield store, created
    for username in created:
        store._execute("DELETE FROM users WHERE username = ?", (username,))
    store._conn.commit()
    store.close()


def a_name(created):
    """A username no other run will have used."""
    username = f"test_{secrets.token_hex(4)}"
    created.append(username)
    return username


def test_it_really_is_talking_to_postgres(store):
    assert dialect_for(DATABASE_URL) is POSTGRES


def test_an_account_registers_and_then_logs_back_in(store):
    store, created = store
    username = a_name(created)

    assert store.register_or_login(username, "secret") == START_RATING
    assert store.register_or_login(username, "secret") == START_RATING  # the hash matched
    assert store.register_or_login(username, "guess") is None


def test_ratings_round_trip_through_the_server(store):
    store, created = store
    winner, loser = a_name(created), a_name(created)
    store.register_or_login(winner, "a")
    store.register_or_login(loser, "b")

    store.record_win(winner, loser)

    assert store.get_rating(winner) == 1216
    assert store.get_rating(loser) == 1184


def test_a_rating_survives_a_new_connection(store):
    """The point of the whole stage: the data outlives the process that wrote it."""
    store, created = store
    username = a_name(created)
    store.register_or_login(username, "secret")
    store.set_rating(username, 1250)

    reconnected = UserStore(DATABASE_URL)
    assert reconnected.register_or_login(username, "secret") == 1250
    reconnected.close()
