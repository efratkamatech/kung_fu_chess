"""Tests for UserStore: accounts, password hashing, ratings (in-memory SQLite)."""

from pathlib import Path

from kfchess.config import START_RATING
from kfchess.server.user_store import (
    POSTGRES,
    SQLITE,
    UserStore,
    dialect_for,
    spell,
)


def a_store():
    return UserStore(":memory:")


def test_a_first_login_registers_the_account_at_the_starting_rating():
    store = a_store()
    assert store.register_or_login("Efrat", "secret") == START_RATING


def test_a_returning_user_with_the_right_password_logs_in():
    store = a_store()
    store.register_or_login("Efrat", "secret")
    assert store.register_or_login("Efrat", "secret") == START_RATING


def test_a_wrong_password_is_rejected():
    store = a_store()
    store.register_or_login("Efrat", "secret")
    assert store.register_or_login("Efrat", "guess") is None


def test_the_password_is_not_stored_in_the_clear():
    store = a_store()
    store.register_or_login("Efrat", "secret")
    stored = store._conn.execute("SELECT salt, pw_hash FROM users").fetchone()
    assert b"secret" not in stored[1]  # only a salted hash is kept, never the password


def test_get_and_set_rating_round_trip():
    store = a_store()
    store.register_or_login("Efrat", "secret")
    store.set_rating("Efrat", 1300)
    assert store.get_rating("Efrat") == 1300


def test_record_win_moves_both_ratings():
    store = a_store()
    store.register_or_login("Efrat", "a")   # both start at 1200
    store.register_or_login("Dan", "b")
    store.record_win("Efrat", "Dan")
    assert store.get_rating("Efrat") == 1216
    assert store.get_rating("Dan") == 1184


def test_accounts_persist_across_reopening_the_database(tmp_path):
    db = tmp_path / "users.db"
    first = UserStore(db)
    first.register_or_login("Efrat", "secret")
    first.set_rating("Efrat", 1250)
    first.close()

    reopened = UserStore(db)
    assert reopened.register_or_login("Efrat", "secret") == 1250  # survived the restart
    reopened.close()


# --- picking a backend --------------------------------------------------------

def test_a_path_means_sqlite_and_a_dsn_means_postgres():
    assert dialect_for("users.db") is SQLITE
    assert dialect_for(Path("/var/lib/kfchess/users.db")) is SQLITE
    assert dialect_for(":memory:") is SQLITE
    assert dialect_for("postgresql://kfchess:pw@postgres:5432/kfchess") is POSTGRES
    assert dialect_for("postgres://kfchess@localhost/kfchess") is POSTGRES


def test_a_statement_is_spelled_for_the_backend_it_is_sent_to():
    statement = "UPDATE users SET rating = ? WHERE username = ?"
    assert spell(statement, SQLITE) == statement  # SQLite is the dialect it is written in
    assert spell(statement, POSTGRES) == (
        "UPDATE users SET rating = %s WHERE username = %s"
    )


def test_the_two_backends_name_a_bytes_column_differently():
    # The salt and the hash are raw bytes, and that is the one column type that differs.
    assert SQLITE.blob == "BLOB"
    assert POSTGRES.blob == "BYTEA"


def test_the_default_target_follows_the_configured_database(monkeypatch, tmp_path):
    """``UserStore()`` is what serve() calls; it must land wherever config points."""
    import kfchess.server.user_store as module

    db = tmp_path / "configured.db"
    monkeypatch.setattr(module, "DATABASE_URL", "")
    monkeypatch.setattr(module, "USERS_DB", db)
    store = UserStore()
    store.register_or_login("Efrat", "secret")
    store.close()

    assert db.exists()  # it used the configured path, not a hardcoded one
