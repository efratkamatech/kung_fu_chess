-- 001_initial: the account table, and the archive of finished games.
--
-- Applied automatically the first time the PostgreSQL container initialises its data
-- directory: docker-compose.yml mounts this directory at
-- /docker-entrypoint-initdb.d, which the official image runs in filename order. It is
-- therefore a *first boot* script, not a migration runner -- an existing volume is
-- never re-initialised, so changing this file after the fact changes nothing until the
-- volume is dropped. A real migration tool arrives when there is a second migration.

-- Accounts. Identical in shape to the CREATE TABLE in server/user_store.py, which runs
-- on every start and is what keeps a laptop's SQLite file in step; whichever runs first
-- wins and the other is a no-op. The columns are spelled for PostgreSQL here (BYTEA
-- rather than BLOB) -- the one difference the store's Dialect also names.
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    salt      BYTEA   NOT NULL,
    pw_hash   BYTEA   NOT NULL,
    rating    INTEGER NOT NULL
);

-- Finished games, partitioned by the day they ended.
--
-- Nothing writes to this yet: the shard announces a result over the bus today, and the
-- consumer that persists it belongs to S2 (`game.finished` on JetStream). The table is
-- created now because the *partitioning* is the decision, and it is far cheaper to make
-- before there is data than after: at the volume this design is sized for, a day's games
-- are dropped by detaching one partition instead of by a DELETE that has to walk the
-- whole archive.
CREATE TABLE IF NOT EXISTS games (
    game_id     BIGSERIAL,
    room_id     TEXT,
    white       TEXT        NOT NULL,
    black       TEXT        NOT NULL,
    winner      TEXT,                  -- 'w' / 'b', or NULL for a game with no winner
    white_after INTEGER     NOT NULL,  -- the ratings as they stood after this game,
    black_after INTEGER     NOT NULL,  -- so a history is readable without replaying ELO
    finished_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (game_id, finished_at)  -- a partition key must be part of the key
) PARTITION BY RANGE (finished_at);

-- A catch-all partition, so the first insert cannot fail for want of one. Real daily
-- partitions are created ahead of time by whoever owns the schedule; rows that miss
-- them land here rather than being rejected.
CREATE TABLE IF NOT EXISTS games_default PARTITION OF games DEFAULT;

CREATE INDEX IF NOT EXISTS games_white_idx ON games (white, finished_at DESC);
CREATE INDEX IF NOT EXISTS games_black_idx ON games (black, finished_at DESC);
