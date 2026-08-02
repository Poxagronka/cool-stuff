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


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
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
