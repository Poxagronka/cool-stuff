"""SQLite storage. Raw messages stay untouched; derived keys are recomputable."""

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS message (
  chat_id      INTEGER NOT NULL,
  msg_id       INTEGER NOT NULL,
  sent_at      TEXT    NOT NULL,
  author       TEXT,
  text         TEXT,
  reply_to     INTEGER,
  preview_json TEXT,
  -- said somewhere only the owner can see. a cluster the group also posted
  -- publishes the public half of its context and leaves this half alone
  private      INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (chat_id, msg_id)
);

CREATE TABLE IF NOT EXISTS link (
  id            INTEGER PRIMARY KEY,
  raw_url       TEXT NOT NULL,
  norm_key      TEXT NOT NULL,
  resolved_url  TEXT,
  resolved_key  TEXT,
  canonical_url TEXT,
  canonical_key TEXT,
  cluster_id    INTEGER,
  chat_id       INTEGER NOT NULL,
  msg_id        INTEGER NOT NULL,
  first_seen_at TEXT NOT NULL,
  -- came from somewhere only the owner can see, so it has to earn its way in
  private       INTEGER NOT NULL DEFAULT 0,
  UNIQUE (chat_id, msg_id, raw_url)
);
CREATE INDEX IF NOT EXISTS ix_link_norm ON link(norm_key);
CREATE INDEX IF NOT EXISTS ix_link_res  ON link(resolved_key);
CREATE INDEX IF NOT EXISTS ix_link_can  ON link(canonical_key);

-- One row per deduplicated link cluster: the thing that becomes a note.
CREATE TABLE IF NOT EXISTS entry (
  cluster_id   INTEGER PRIMARY KEY,
  url          TEXT NOT NULL,
  domain       TEXT NOT NULL,
  title        TEXT,
  description  TEXT,
  image        TEXT,
  site_name    TEXT,
  price        TEXT,
  category     TEXT,
  tags         TEXT,
  confidence   TEXT,
  status       TEXT NOT NULL DEFAULT 'new',
  enrich_tier  TEXT,
  http_status  INTEGER,
  note_path    TEXT,
  updated_at   TEXT
);
CREATE INDEX IF NOT EXISTS ix_entry_status ON entry(status);

-- Remembers which ladder tier worked for a domain, to start there next time.
CREATE TABLE IF NOT EXISTS domain_tier (
  domain TEXT PRIMARY KEY,
  tier   TEXT NOT NULL,
  ok     INTEGER NOT NULL DEFAULT 0,
  fail   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS state (
  key   TEXT PRIMARY KEY,
  value TEXT
);
"""


# columns added after the first database went into service. sqlite has no
# "add column if not absent", so the existing ones are read and compared
LATER = [
    ("link", "private", "INTEGER NOT NULL DEFAULT 0"),
    ("message", "private", "INTEGER NOT NULL DEFAULT 0"),
]

# what a new column has to be told about the rows that predate it. every one
# derives its value from data already in the database, so running them on
# every startup costs a scan and changes nothing the second time
BACKFILL = [
    "UPDATE message SET private = 1 WHERE private = 0 AND (chat_id, msg_id) IN"
    " (SELECT chat_id, msg_id FROM link WHERE private = 1)",
]


def migrate(conn: sqlite3.Connection) -> None:
    for table, column, decl in LATER:
        have = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in have:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
    for sql in BACKFILL:
        conn.execute(sql)
    conn.commit()


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    migrate(conn)
    return conn


def get_state(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM state WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO state(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()
